"""Com um conjunto pequeno, todas as consultas têm que dar a mesma resposta nos dois bancos.
É o que garante que o comparativo compara a mesma coisa."""

import os
import uuid

import pytest

from bench import mongo, pg
from bench.compare import same
from bench.data import dataset


@pytest.fixture(scope="module")
def engines():
    names, events = dataset(6000, players=60, seed=7)
    os.environ["BENCH_MONGO_DB"] = f"bench_test_{uuid.uuid4().hex[:8]}"
    conn, db = pg.connect(), mongo.connect()
    pg.load(conn, names, events)
    mongo.load(db, names, events)
    yield conn, db, names, events
    db.client.drop_database(db.name)
    conn.execute("DROP TABLE IF EXISTS events; DROP TABLE IF EXISTS players;")
    conn.close()


@pytest.mark.parametrize("query", ["weapons", "deaths_by_hour", "heatmap", "sessions", "kd"])
def test_aggregations_match(engines, query):
    conn, db, _, _ = engines
    a, b = getattr(pg, query)(conn), getattr(mongo, query)(db)
    assert len(a) > 0
    assert same(a, b)


def test_history_matches(engines):
    conn, db, names, _ = engines
    pid = next(iter(names))
    assert same(pg.history(conn, pid), mongo.history(db, pid))


def test_counts_match_the_dataset(engines):
    conn, db, _, events = engines
    assert conn.execute("SELECT COUNT(*) FROM events").fetchone()[0] == len(events) == db.events.count_documents({})
    kills = sum(1 for e in events if e.type == "kill")
    assert sum(r[1] for r in pg.weapons(conn)) == kills


def test_rename_touches_one_row_vs_many_documents(engines):
    conn, db, _, events = engines
    pid = events[0].player_id
    involved = sum(1 for e in events if e.player_id == pid) + sum(1 for e in events if e.killer_id == pid)
    assert pg.rename(conn, pid, "Outro Nome") == 1
    assert mongo.rename(db, pid, "Outro Nome") == involved
    assert same(pg.history(conn, pid), mongo.history(db, pid))


def test_dataset_is_deterministic():
    a = dataset(500, players=20, seed=3)
    b = dataset(500, players=20, seed=3)
    assert a == b
