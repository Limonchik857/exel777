"""Построение отчёта по данным: KPI-карточки, таблица и SVG-графики."""

import math

import pandas as pd

from quality.services import analyze_quality


def _clean_value(value):
    if value is None or pd.isna(value):
        return ""
    return str(value)


def kpi_cards(df):
    """KPI-карточки для сводки."""
    quality = analyze_quality(df)
    rows = len(df)
    cols = len(df.columns)
    total_cells = rows * cols
    return [
        {"label": "Строк", "value": rows, "hint": "всего записей"},
        {"label": "Столбцов", "value": cols, "hint": "полей"},
        {
            "label": "Заполненность",
            "value": f"{quality['fill_rate']:.1f}%",
            "hint": "непустых ячеек",
        },
        {
            "label": "Дубликаты",
            "value": quality["duplicates"],
            "hint": "полностью совпадающих строк",
        },
        {
            "label": "Quality Score",
            "value": quality["score"],
            "hint": "из 100",
            "status": quality["status"],
        },
        {"label": "Пустых ячеек", "value": quality["empty_values"], "hint": "из %d" % total_cells},
    ]


def chart_bar(df, column, limit=12):
    """Столбчатая диаграмма: частоты значений категориального столбца (топ)."""
    series = df[column].map(_clean_value)
    counts = series[series != ""].value_counts().head(limit)
    if counts.empty:
        return None
    return _svg_bar(counts)


def chart_line(df, column, limit=30):
    """Линейная диаграмма: значения числового столбца по порядку строк."""
    numeric = pd.to_numeric(df[column], errors="coerce").dropna()
    if numeric.empty:
        return None
    values = numeric.head(limit)
    return _svg_line(values)


def chart_pie(df, column, limit=8):
    """Круговая диаграмма: доли значений категориального столбца (топ)."""
    series = df[column].map(_clean_value)
    counts = series[series != ""].value_counts().head(limit)
    if counts.empty:
        return None
    return _svg_pie(counts)


def _svg_bar(counts):
    width, height, pad = 560, 220, 30
    n = len(counts)
    values = [int(v) for v in counts.values]
    max_v = max(values) or 1
    plot_w = width - pad - 20
    plot_h = height - pad - 20
    bar_w = plot_w / n * 0.7
    gap = plot_w / n
    parts = [
        f'<svg viewBox="0 0 {width} {height}" xmlns="http://www.w3.org/2000/svg" '
        'role="img" aria-label="Столбчатая диаграмма">'
        '<rect width="100%" height="100%" fill="transparent"/>'
    ]
    for i, (label, value) in enumerate(zip(counts.index, values)):
        bar_h = plot_h * value / max_v
        x = pad + i * gap + (gap - bar_w) / 2
        y = height - pad - bar_h
        parts.append(
            f'<rect x="{x:.1f}" y="{y:.1f}" width="{bar_w:.1f}" height="{bar_h:.1f}" '
            f'rx="3" fill="#6fa0ff" opacity="0.9"/>'
        )
        parts.append(
            f'<text x="{x + bar_w / 2:.1f}" y="{height - pad + 14:.1f}" '
            f'font-family="JetBrains Mono, monospace" font-size="10" fill="#8b93a7" '
            f'text-anchor="middle">{_short(label)}</text>'
        )
        parts.append(
            f'<text x="{x + bar_w / 2:.1f}" y="{y - 4:.1f}" '
            f'font-family="JetBrains Mono, monospace" font-size="10" fill="#cdd3df" '
            f'text-anchor="middle">{value}</text>'
        )
    parts.append("</svg>")
    return "".join(parts)


def _svg_line(values):
    width, height, pad = 560, 220, 30
    vals = [float(v) for v in values]
    min_v, max_v = min(vals), max(vals)
    span = (max_v - min_v) or 1
    n = len(vals)
    plot_w = width - pad - 20
    plot_h = height - pad - 20
    points = []
    for i, v in enumerate(vals):
        x = pad + plot_w * i / (n - 1 if n > 1 else 1)
        y = height - pad - plot_h * (v - min_v) / span
        points.append(f"{x:.1f},{y:.1f}")
    path = " ".join(f"L {p}" for p in points[1:]) or ""
    parts = [
        f'<svg viewBox="0 0 {width} {height}" xmlns="http://www.w3.org/2000/svg" '
        'role="img" aria-label="Линейная диаграмма">',
        '<polyline points="' + " ".join(points) + '" fill="none" stroke="#ffb454" '
        f'stroke-width="2.5" stroke-linejoin="round" stroke-linecap="round"/>',
    ]
    for p, v in zip(points, vals):
        x, y = p.split(",")
        parts.append(
            f'<circle cx="{x}" cy="{y}" r="3" fill="#ffb454"/>'
            f'<text x="{x}" y="{float(y) - 8:.1f}" font-family="JetBrains Mono, monospace" '
            f'font-size="9" fill="#cdd3df" text-anchor="middle">{v:g}</text>'
        )
    parts.append("</svg>")
    return "".join(parts)


def _svg_pie(counts):
    width, height = 300, 220
    cx, cy, r = 110, 110, 80
    total = sum(int(v) for v in counts.values)
    colors = ["#6fa0ff", "#ffb454", "#3fbf7f", "#b48bfa", "#ff5c57", "#e4be4f", "#45a5c5", "#8b93a7"]
    parts = [
        f'<svg viewBox="0 0 {width} {height}" xmlns="http://www.w3.org/2000/svg" '
        'role="img" aria-label="Круговая диаграмма">'
    ]
    start = 0.0
    legend_y = 18
    for i, (label, value) in enumerate(zip(counts.index, counts.values)):
        frac = int(value) / total
        end = start + frac * 360
        large = 1 if (end - start) > 180 else 0
        x1 = cx + r * math.cos(math.radians(start))
        y1 = cy + r * math.sin(math.radians(start))
        x2 = cx + r * math.cos(math.radians(end))
        y2 = cy + r * math.sin(math.radians(end))
        color = colors[i % len(colors)]
        parts.append(
            f'<path d="M {cx} {cy} L {x1:.1f} {y1:.1f} A {r} {r} 0 {large} 1 {x2:.1f} {y2:.1f} Z" '
            f'fill="{color}" opacity="0.9"/>'
        )
        # Легенда справа
        lx = width - 120
        parts.append(
            f'<rect x="{lx}" y="{legend_y - 10}" width="10" height="10" rx="2" fill="{color}"/>'
            f'<text x="{lx + 16}" y="{legend_y}" font-family="Inter, sans-serif" font-size="11" '
            f'fill="#cdd3df">{_short(label)} · {frac * 100:.0f}%</text>'
        )
        legend_y += 22
        start = end
    parts.append("</svg>")
    return "".join(parts)


def _short(text, limit=10):
    text = str(text)
    return text if len(text) <= limit else text[: limit - 1] + "…"


def report_table(df, limit=50):
    """Таблица для отчёта (первые limit строк)."""
    preview = df.head(limit)
    columns = [str(c) for c in preview.columns]
    rows = [
        {col: _clean_value(row[col]) for col in df.columns}
        for _, row in preview.iterrows()
    ]
    return {"columns": columns, "rows": rows}


def column_choices(df):
    """Список столбцов с определённым типом для выбора диаграмм."""
    return list(df.columns)


def detect_kind(df, column):
    """Возвращает тип столбца: numeric / date / text."""
    from quality.services import _candidate_date_columns

    series = df[column]
    numeric = pd.to_numeric(series.dropna(), errors="coerce")
    if numeric.notna().mean() if len(numeric) else 0 >= 0.6:
        return "numeric"
    if column in _candidate_date_columns(df):
        return "date"
    return "text"