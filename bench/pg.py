"""PostgreSQL, modelo normalizado: o nome do jogador mora só na tabela players."""

from __future__ import annotations

import os

import psycopg

from .data import Event

SCHEMA = """
DROP TABLE IF EXISTS events;
DROP TABLE IF EXISTS players;
CREATE TABLE players (
    id   TEXT PRIMARY KEY,
    name TEXT NOT NULL
);
CREATE TABLE events (
    id        BIGSERIAL PRIMARY KEY,
    type      TEXT NOT NULL CHECK (type IN ('kill','death','hit','connect','disconnect')),
    ts        TIMESTAMP(3) NOT NULL,
    player_id TEXT NOT NULL REFERENCES players (id),
    x         DOUBLE PRECISION,
    y         DOUBLE PRECISION,
    killer_id TEXT REFERENCES players (id),
    weapon    TEXT,
    distance  DOUBLE PRECISION,
    part      TEXT,
    damage    DOUBLE PRECISION,
    source    TEXT
);
"""

INDEXES = """
CREATE INDEX events_type_ts   ON events (type, ts DESC);
CREATE INDEX events_player_ts ON events (player_id, ts DESC);
CREATE INDEX events_killer_ts ON events (killer_id, ts DESC) WHERE killer_id IS NOT NULL;
ANALYZE events;
ANALYZE players;
"""


def connect() -> psycopg.Connection:
    dsn = os.environ.get("BENCH_PG", "host=127.0.0.1 dbname=bench user=bench password=bench_dev")
    return psycopg.connect(dsn, autocommit=True)


def load(conn: psycopg.Connection, names: dict[str, str], events: list[Event]) -> None:
    conn.execute(SCHEMA)
    # COPY é o jeito rápido de carregar em massa no Postgres (bem mais que INSERT linha a linha)
    with conn.cursor() as cur:
        with cur.copy("COPY players (id, name) FROM STDIN") as copy:
            for pid, name in names.items():
                copy.write_row((pid, name))
        with cur.copy("COPY events (type, ts, player_id, x, y, killer_id, weapon, distance, part, damage, source) "
                      "FROM STDIN") as copy:
            for e in events:
                copy.write_row((e.type, e.ts, e.player_id, e.x, e.y, e.killer_id, e.weapon, e.distance,
                                e.part, e.damage, e.source))
    conn.execute(INDEXES)


def history(conn, player_id: str):
    return conn.execute("""
        SELECT e.type, e.ts, e.x, e.y, p.name
        FROM events e JOIN players p ON p.id = e.player_id
        WHERE e.player_id = %s
        ORDER BY e.ts DESC LIMIT 50
    """, (player_id,)).fetchall()


def weapons(conn):
    return conn.execute("""
        SELECT weapon, COUNT(*), AVG(distance), MAX(distance)
        FROM events WHERE type = 'kill' GROUP BY weapon
    """).fetchall()


def deaths_by_hour(conn):
    return conn.execute("""
        SELECT EXTRACT(HOUR FROM ts)::int, COUNT(*)
        FROM events WHERE type = 'death' GROUP BY 1
    """).fetchall()


def heatmap(conn, cell: int = 512):
    return conn.execute("""
        SELECT FLOOR(x / %(c)s)::int, FLOOR(y / %(c)s)::int, COUNT(*)
        FROM events WHERE type = 'kill' AND x IS NOT NULL GROUP BY 1, 2
    """, {"c": cell}).fetchall()


def sessions(conn):
    # LAG() olha o evento anterior do mesmo jogador; desconexão logo depois de conexão é uma sessão
    return conn.execute("""
        WITH ordered AS (
            SELECT player_id, type, ts,
                   LAG(type) OVER w AS prev_type,
                   LAG(ts)   OVER w AS prev_ts
            FROM events
            WHERE type IN ('connect', 'disconnect')
            WINDOW w AS (PARTITION BY player_id ORDER BY ts)
        )
        SELECT player_id, COUNT(*), ROUND(SUM(EXTRACT(EPOCH FROM ts - prev_ts) * 1000))::bigint
        FROM ordered
        WHERE type = 'disconnect' AND prev_type = 'connect'
        GROUP BY player_id
    """).fetchall()


def kd(conn):
    return conn.execute("""
        SELECT p.id, COALESCE(k.kills, 0), COALESCE(d.deaths, 0)
        FROM players p
        LEFT JOIN (SELECT killer_id, COUNT(*) AS kills FROM events WHERE type = 'kill' GROUP BY killer_id) k
               ON k.killer_id = p.id
        LEFT JOIN (SELECT player_id, COUNT(*) AS deaths FROM events WHERE type = 'death' GROUP BY player_id) d
               ON d.player_id = p.id
        WHERE k.kills IS NOT NULL OR d.deaths IS NOT NULL
    """).fetchall()


def rename(conn, player_id: str, name: str) -> int:
    """Normalizado: trocar o nome é mexer em uma linha."""
    return conn.execute("UPDATE players SET name = %s WHERE id = %s", (name, player_id)).rowcount


def size_bytes(conn) -> dict[str, int]:
    data, idx = conn.execute("""
        SELECT SUM(pg_table_size(c.oid)), SUM(pg_indexes_size(c.oid))
        FROM pg_class c WHERE c.relname IN ('events', 'players')
    """).fetchone()
    return {"data": int(data), "indexes": int(idx)}
