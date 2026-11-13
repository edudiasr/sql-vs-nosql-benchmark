"""Gera o mesmo conjunto de eventos pros dois bancos (semente fixa).

Os horários têm milissegundos aleatórios: com segundos inteiros apareciam empates no
horário de eventos do mesmo jogador, e cada banco desempatava de um jeito."""

from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import datetime, timedelta

HOTSPOTS = [(6700, 2500, 6), (10300, 2300, 5), (12900, 9500, 4), (4500, 10200, 5),
            (6100, 7700, 3), (1700, 14000, 3), (2700, 5200, 3), (13900, 13300, 2)]
WEAPONS = [("M4-A1", 40, 300), ("AKM", 30, 250), ("Mosin9130", 100, 800), ("SVD", 150, 900),
           ("MP5K", 5, 60), ("Shotgun", 2, 25), ("FX-45", 3, 40)]
PARTS = ["Torso", "Head", "LeftArm", "RightArm", "LeftLeg", "RightLeg"]
SOURCES = ["Infectado", "player", "ai", "animal"]


@dataclass(frozen=True)
class Event:
    type: str
    ts: datetime
    player_id: str
    x: float | None = None
    y: float | None = None
    killer_id: str | None = None
    weapon: str | None = None
    distance: float | None = None
    part: str | None = None
    damage: float | None = None
    source: str | None = None


def dataset(count: int, players: int = 2000, seed: int = 42,
            end: datetime = datetime(2026, 11, 13)) -> tuple[dict[str, str], list[Event]]:
    rng = random.Random(seed)
    start = end - timedelta(days=30)
    span_ms = int((end - start).total_seconds() * 1000)
    ids = [f"p{i:05d}" for i in range(players)]
    names = {pid: f"Jogador{i:05d}" for i, pid in enumerate(ids)}
    skill = [rng.random() ** 2 for _ in ids]

    def when() -> datetime:
        return start + timedelta(milliseconds=rng.randrange(span_ms))

    def spot() -> tuple[float, float]:
        x, y, _ = rng.choices(HOTSPOTS, weights=[h[2] for h in HOTSPOTS])[0]
        return (round(min(15359.0, max(0.0, rng.gauss(x, 500))), 1),
                round(min(15359.0, max(0.0, rng.gauss(y, 500))), 1))

    events: list[Event] = []
    while len(events) < count:
        roll = rng.random()
        if roll < 0.25:
            killer = rng.choices(ids, weights=skill)[0]
            victim = rng.choice(ids)
            if killer == victim:
                continue
            weapon, lo, hi = rng.choice(WEAPONS)
            x, y = spot()
            events.append(Event("kill", when(), victim, x, y, killer, weapon, round(rng.uniform(lo, hi), 1)))
        elif roll < 0.45:
            x, y = spot()
            events.append(Event("death", when(), rng.choice(ids), x, y))
        elif roll < 0.75:
            x, y = spot()
            events.append(Event("hit", when(), rng.choice(ids), x, y, part=rng.choice(PARTS),
                                damage=round(rng.uniform(1, 60), 2), source=rng.choice(SOURCES)))
        else:
            pid = rng.choice(ids)
            t = when()
            events.append(Event("connect", t, pid))
            events.append(Event("disconnect", t + timedelta(milliseconds=rng.randrange(300_000, 10_800_000)), pid))
    return names, events[:count]
