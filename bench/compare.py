"""Deixa os resultados dos dois bancos no mesmo formato pra poder comparar."""

from __future__ import annotations

from datetime import datetime


def normalize(rows) -> list[tuple]:
    def value(v):
        if isinstance(v, float):
            return round(v, 6)
        if isinstance(v, datetime):
            return v.replace(microsecond=v.microsecond // 1000 * 1000, tzinfo=None)
        if hasattr(v, "__float__") and not isinstance(v, (int, bool)):
            return round(float(v), 6)  # Decimal do Postgres
        return v

    return sorted(tuple(value(v) for v in row) for row in rows)


def same(a, b) -> bool:
    return normalize(a) == normalize(b)
