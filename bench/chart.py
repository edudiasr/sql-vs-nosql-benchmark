"""Gráfico de barras em SVG (sem biblioteca): tempo de cada consulta nos dois bancos."""

from __future__ import annotations

import math

PG = "#60a5fa"
MONGO = "#34d399"


def render(results: dict, width: int = 760) -> str:
    rows = results["queries"]
    label_w, pad, bar_h, gap = 250, 16, 14, 14
    plot_w = width - label_w - pad * 2 - 70
    height = 70 + len(rows) * (bar_h * 2 + gap) + 30
    peak = max(max(r["postgres_ms"], r["mongodb_ms"]) for r in rows)
    scale = lambda ms: plot_w * math.log10(1 + ms) / math.log10(1 + peak)  # noqa: E731

    parts = [f'<rect width="{width}" height="{height}" fill="#06080f"/>',
             f'<text x="{pad}" y="28" font-size="15" font-weight="700" fill="#e8eef8">'
             f'Tempo por consulta · {results["events"]:,} eventos'.replace(",", ".") + '</text>',
             f'<rect x="{pad}" y="40" width="10" height="10" fill="{PG}"/><text x="{pad + 15}" y="49" fill="#cbd5e1">PostgreSQL</text>',
             f'<rect x="{pad + 110}" y="40" width="10" height="10" fill="{MONGO}"/><text x="{pad + 125}" y="49" fill="#cbd5e1">MongoDB</text>',
             f'<text x="{width - pad}" y="49" text-anchor="end" fill="#64748b">ms, escala log (menor é melhor)</text>']

    y = 70
    for r in rows:
        parts.append(f'<text x="{pad}" y="{y + bar_h + 4}" fill="#e8eef8">{r["title"]}</text>')
        for i, (ms, color) in enumerate(((r["postgres_ms"], PG), (r["mongodb_ms"], MONGO))):
            by = y + i * bar_h
            w = max(2, scale(ms))
            parts.append(f'<rect x="{label_w}" y="{by}" width="{w:.1f}" height="{bar_h - 2}" rx="3" fill="{color}"/>')
            parts.append(f'<text x="{label_w + w + 6:.1f}" y="{by + bar_h - 3}" fill="#94a3b8">{ms:g}</text>')
        y += bar_h * 2 + gap

    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" width="{width}" height="{height}" '
            f'font-family="system-ui, sans-serif" font-size="12">{"".join(parts)}</svg>\n')
