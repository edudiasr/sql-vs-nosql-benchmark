"""Roda o comparativo: python -m bench.run --events 300000

Carrega os mesmos eventos nos dois bancos, confere que cada consulta devolve a mesma resposta
nos dois e mede o tempo (mediana de várias rodadas, depois de uma rodada de aquecimento)."""

from __future__ import annotations

import argparse
import json
import platform
import statistics
import time
from pathlib import Path

from . import mongo, pg
from .chart import render
from .compare import same
from .data import dataset

QUERIES = [
    ("history", "histórico de um jogador (50 últimos)"),
    ("weapons", "kills por arma (GROUP BY)"),
    ("deaths_by_hour", "mortes por hora do dia"),
    ("heatmap", "mapa de calor (grade de 512 m)"),
    ("sessions", "sessões por jogador (função de janela)"),
    ("kd", "kills e mortes por jogador"),
]


def timed(fn, reps: int) -> tuple[float, object]:
    result = fn()  # aquecimento: carrega índice e dados na memória
    samples = []
    for _ in range(reps):
        started = time.perf_counter()
        result = fn()
        samples.append((time.perf_counter() - started) * 1000)
    return statistics.median(samples), result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--events", type=int, default=300_000)
    parser.add_argument("--players", type=int, default=2000)
    parser.add_argument("--reps", type=int, default=5)
    parser.add_argument("--out", type=Path, default=Path("results"))
    args = parser.parse_args()
    args.out.mkdir(exist_ok=True)

    names, events = dataset(args.events, args.players)
    conn, db = pg.connect(), mongo.connect()

    results: dict = {"events": len(events), "players": len(names), "reps": args.reps, "queries": [], "load": {}}

    for engine, load in (("postgres", lambda: pg.load(conn, names, events)), ("mongodb", lambda: mongo.load(db, names, events))):
        started = time.perf_counter()
        load()
        results["load"][engine] = round(time.perf_counter() - started, 2)
        print(f"carga {engine}: {results['load'][engine]} s")

    # um jogador com bastante evento pra consulta de histórico
    busy = max(names, key=lambda pid: sum(1 for e in events[:20000] if e.player_id == pid))

    for key, title in QUERIES:
        args_ = (busy,) if key == "history" else ()
        pg_ms, pg_rows = timed(lambda: getattr(pg, key)(conn, *args_), args.reps)
        mg_ms, mg_rows = timed(lambda: getattr(mongo, key)(db, *args_), args.reps)
        ok = same(pg_rows, mg_rows)
        results["queries"].append({"key": key, "title": title, "postgres_ms": round(pg_ms, 1),
                                   "mongodb_ms": round(mg_ms, 1), "rows": len(pg_rows), "same_result": ok})
        print(f"{title:45s} pg {pg_ms:8.1f} ms   mongo {mg_ms:8.1f} ms   linhas {len(pg_rows):5d}   "
              f"{'igual' if ok else 'DIFERENTE'}")
        if not ok:
            raise SystemExit(f"resultado diferente em {key}")

    # trocar o nome de um jogador: 1 linha no modelo normalizado, N documentos no desnormalizado
    pg_ms, pg_rows = timed(lambda: pg.rename(conn, busy, "Renomeado"), args.reps)
    mg_ms, mg_docs = timed(lambda: mongo.rename(db, busy, f"Renomeado{time.perf_counter_ns()}"), args.reps)
    results["rename"] = {"postgres_ms": round(pg_ms, 2), "postgres_rows": pg_rows,
                         "mongodb_ms": round(mg_ms, 2), "mongodb_docs": mg_docs}
    print(f"renomear jogador: pg {pg_ms:.2f} ms ({pg_rows} linha)   mongo {mg_ms:.2f} ms ({mg_docs} documentos)")

    results["size"] = {"postgres": pg.size_bytes(conn), "mongodb": mongo.size_bytes(db)}
    results["versions"] = {
        "postgres": conn.execute("SHOW server_version").fetchone()[0].split()[0],
        "mongodb": db.client.server_info()["version"],
        "python": platform.python_version(),
    }

    (args.out / "results.json").write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    (args.out / "chart.svg").write_text(render(results), encoding="utf-8")
    print(f"resultados em {args.out}/")


if __name__ == "__main__":
    main()
