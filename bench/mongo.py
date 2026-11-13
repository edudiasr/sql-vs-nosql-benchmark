"""MongoDB, modelo em documento: o nome do jogador vai copiado dentro de cada evento,
que é o jeito comum de modelar pra leitura rápida sem join."""

from __future__ import annotations

import os

from pymongo import ASCENDING, DESCENDING, MongoClient
from pymongo.database import Database

from .data import Event

BATCH = 10_000


def connect() -> Database:
    client = MongoClient(os.environ.get("BENCH_MONGO", "mongodb://127.0.0.1:27017"))
    return client[os.environ.get("BENCH_MONGO_DB", "bench")]


def _doc(e: Event, names: dict[str, str]) -> dict:
    doc: dict = {"type": e.type, "ts": e.ts, "player": {"id": e.player_id, "name": names[e.player_id]}}
    if e.x is not None:
        doc["pos"] = [e.x, e.y]
    if e.killer_id:
        doc["killer"] = {"id": e.killer_id, "name": names[e.killer_id]}
    for field in ("weapon", "distance", "part", "damage", "source"):
        value = getattr(e, field)
        if value is not None:
            doc[field] = value
    return doc


def load(db: Database, names: dict[str, str], events: list[Event]) -> None:
    db.events.drop()
    batch: list[dict] = []
    for e in events:
        batch.append(_doc(e, names))
        if len(batch) == BATCH:
            db.events.insert_many(batch, ordered=False)
            batch = []
    if batch:
        db.events.insert_many(batch, ordered=False)
    db.events.create_index([("type", ASCENDING), ("ts", DESCENDING)], name="type_ts")
    db.events.create_index([("player.id", ASCENDING), ("ts", DESCENDING)], name="player_ts")
    db.events.create_index([("killer.id", ASCENDING), ("ts", DESCENDING)], name="killer_ts", sparse=True)


def history(db: Database, player_id: str):
    return [(d["type"], d["ts"], *(d.get("pos") or (None, None)), d["player"]["name"])
            for d in db.events.find({"player.id": player_id}).sort("ts", -1).limit(50)]


def weapons(db: Database):
    return [(d["_id"], d["n"], d["avg"], d["max"]) for d in db.events.aggregate([
        {"$match": {"type": "kill"}},
        {"$group": {"_id": "$weapon", "n": {"$sum": 1}, "avg": {"$avg": "$distance"}, "max": {"$max": "$distance"}}},
    ])]


def deaths_by_hour(db: Database):
    return [(d["_id"], d["n"]) for d in db.events.aggregate([
        {"$match": {"type": "death"}},
        {"$group": {"_id": {"$hour": "$ts"}, "n": {"$sum": 1}}},
    ])]


def heatmap(db: Database, cell: int = 512):
    return [(int(d["_id"]["x"]), int(d["_id"]["y"]), d["n"]) for d in db.events.aggregate([
        {"$match": {"type": "kill", "pos": {"$exists": True}}},
        {"$group": {"_id": {"x": {"$floor": {"$divide": [{"$arrayElemAt": ["$pos", 0]}, cell]}},
                            "y": {"$floor": {"$divide": [{"$arrayElemAt": ["$pos", 1]}, cell]}}},
                    "n": {"$sum": 1}}},
    ])]


def sessions(db: Database):
    return [(d["_id"], d["n"], d["ms"]) for d in db.events.aggregate([
        {"$match": {"type": {"$in": ["connect", "disconnect"]}}},
        {"$setWindowFields": {
            "partitionBy": "$player.id", "sortBy": {"ts": 1},
            "output": {"prev": {"$shift": {"output": {"type": "$type", "ts": "$ts"}, "by": -1}}},
        }},
        {"$match": {"type": "disconnect", "prev.type": "connect"}},
        {"$group": {"_id": "$player.id", "n": {"$sum": 1},
                    "ms": {"$sum": {"$dateDiff": {"startDate": "$prev.ts", "endDate": "$ts", "unit": "millisecond"}}}}},
    ], allowDiskUse=True)]


def kd(db: Database):
    return [(d["_id"], d["kills"], d["deaths"]) for d in db.events.aggregate([
        {"$match": {"type": "kill"}},
        {"$project": {"_id": 0, "id": "$killer.id", "kills": {"$literal": 1}, "deaths": {"$literal": 0}}},
        {"$unionWith": {"coll": "events", "pipeline": [
            {"$match": {"type": "death"}},
            {"$project": {"_id": 0, "id": "$player.id", "kills": {"$literal": 0}, "deaths": {"$literal": 1}}},
        ]}},
        {"$group": {"_id": "$id", "kills": {"$sum": "$kills"}, "deaths": {"$sum": "$deaths"}}},
    ], allowDiskUse=True)]


def rename(db: Database, player_id: str, name: str) -> int:
    """Desnormalizado: o nome está copiado em cada evento do jogador (como vítima e como matador)."""
    a = db.events.update_many({"player.id": player_id}, {"$set": {"player.name": name}}).modified_count
    b = db.events.update_many({"killer.id": player_id}, {"$set": {"killer.name": name}}).modified_count
    return a + b


def size_bytes(db: Database) -> dict[str, int]:
    stats = db.command("collStats", "events")
    return {"data": int(stats["storageSize"]), "indexes": int(stats["totalIndexSize"])}
