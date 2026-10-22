#!/usr/bin/env python3
"""Render a validated, real 53-week contribution calendar as a standalone SVG.

Only the standard library and common.py are used. Set STATIC=1 to emit the final
frame without animation. Future dates are outlined and are never counted as
zero-contribution observations.
"""

from __future__ import annotations

import argparse
from datetime import date, timedelta
import json
from pathlib import Path
from typing import Any

from common import ACCENT, BG, BORDER, FG, LEVELS, MUTED, ROOT, Panel, node

WIDTH, HEIGHT = 1060, 350
GRID_X, GRID_Y = 76, 125
CELL, GAP = 14, 4
STEP = CELL + GAP
MONTHS = ("", "Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


def validate_data(data: dict[str, Any]) -> None:
    """Check the cached JSON before drawing, including continuity and 53 columns."""
    if data.get("schema_version") != 1 or data.get("week_count") != 53:
        raise ValueError("Expected calendar schema 1 and exactly 53 weeks.")
    first, last, start = (date.fromisoformat(data[key]) for key in ("calendar_start", "calendar_end", "grid_start"))
    if start.weekday() != 6 or not 0 <= (first - start).days <= 6:
        raise ValueError("Calendar grid must start on the Sunday of its first observed week.")
    if (last - start).days // 7 != 52:
        raise ValueError("The source dates do not occupy 53 calendar columns.")
    days = data.get("days", [])
    if len(days) != (last - first).days + 1:
        raise ValueError("Cached contribution dates are incomplete.")
    for offset, item in enumerate(days):
        if date.fromisoformat(item["date"]) != first + timedelta(days=offset):
            raise ValueError("Cached contribution dates are duplicated, missing, or unsorted.")
        count, level = item["count"], item["level"]
        if type(count) is not int or count < 0 or type(level) is not int or not 0 <= level <= 4:
            raise ValueError("Cached contribution counts/levels are invalid.")
        if (count == 0) != (level == 0):
            raise ValueError("Cached contribution count and level disagree.")
    source_total = data.get("source_total")
    if source_total is not None and source_total != sum(day["count"] for day in days):
        raise ValueError("Cached source total does not match the daily counts.")


def calendar_cells(data: dict[str, Any]) -> list[dict[str, Any]]:
    """Return 371 dated positions; absent boundary days have count/level None."""
    validate_data(data)
    observed = {item["date"]: item for item in data["days"]}
    start = date.fromisoformat(data["grid_start"])
    result = []
    for offset in range(53 * 7):
        iso = (start + timedelta(days=offset)).isoformat()
        item = observed.get(iso)
        result.append({
            "date": iso, "column": offset // 7, "row": offset % 7,
            "observed": item is not None,
            "count": None if item is None else item["count"],
            "level": None if item is None else item["level"],
        })
    return result


def calendar_stats(data: dict[str, Any]) -> dict[str, int]:
    """Statistics are over observed source days, never an all-time claim."""
    days = data["days"]
    total = sum(day["count"] for day in days)
    active = sum(day["count"] > 0 for day in days)
    longest = run = 0
    for day in days:
        run = run + 1 if day["count"] else 0
        longest = max(longest, run)
    # Today's uncompleted day does not break a streak that ended yesterday.
    cursor = len(days) - 1
    if cursor >= 0 and not days[cursor]["count"]:
        cursor -= 1
    current = 0
    while cursor >= 0 and days[cursor]["count"]:
        current += 1
        cursor -= 1
    return {"total": total, "active_days": active, "longest_streak": longest, "current_streak": current}


def month_labels(data: dict[str, Any]) -> list[tuple[float, str]]:
    start, end = date.fromisoformat(data["grid_start"]), date.fromisoformat(data["calendar_end"])
    candidates: list[tuple[float, str]] = []
    cursor = start
    while cursor <= end:
        if cursor == start or cursor.day == 1:
            column = (cursor - start).days // 7
            label = MONTHS[cursor.month]
            if cursor.month == 1:
                label += f" '{cursor.year % 100:02d}"
            candidates.append((GRID_X + column * STEP, label))
        cursor += timedelta(days=1)
    # A short first partial month must not overlap the next month's label.
    result = []
    for i, (x, label) in enumerate(candidates):
        width = len(label) * 10.5 * .61
        if i + 1 < len(candidates) and x + width + 9 > candidates[i + 1][0]:
            continue
        if x + width <= WIDTH - 24:
            result.append((x, label))
    return result


def render_heatmap(data: dict[str, Any], output: Path | str) -> Panel:
    cells = calendar_cells(data)
    stats = calendar_stats(data)
    description = (
        f"Public GitHub contributions for {data['username']}, {data['calendar_start']} through "
        f"{data['calendar_end']} (UTC). {stats['total']} contributions on {stats['active_days']} active days. "
        "Counts come from GitHub's per-day tooltips; colours use its supplied levels. "
        "Statistics cover this observed calendar window. Current streak is measured at the final "
        "source date, allowing the preceding day if the final day has no contributions. "
        "The calendar reveals once diagonally and remains visible."
    )
    panel = Panel(WIDTH, HEIGHT, f"~/@{data['username']} · contributions", description)
    panel.text(24, 73, "Contribution activity", size=20, fill=FG)
    panel.text(WIDTH - 24, 71, "53 WEEKS · PUBLIC GITHUB", size=10.5, fill=ACCENT, anchor="end")
    panel.text(24, 94, f"{data['calendar_start']} → {data['calendar_end']} · UTC", size=11, fill=MUTED)

    for x, label in month_labels(data):
        panel.text(x, 114, label, size=10.5, fill=MUTED)
    for row, label in [(1, "Mon"), (3, "Wed"), (5, "Fri")]:
        panel.text(31, GRID_Y + row * STEP + 11, label, size=10.5, fill=MUTED)

    for item in cells:
        x, y = GRID_X + item["column"] * STEP, GRID_Y + item["row"] * STEP
        attrs: dict[str, Any] = {
            "data_date": item["date"], "data_observed": str(item["observed"]).lower(),
        }
        if item["observed"]:
            attrs.update(data_count=item["count"], data_level=item["level"])
            rect = panel.rect(x, y, CELL, CELL, LEVELS[item["level"]], rx=2, **attrs)
            count = item["count"]
            detail = f"{count:,} contribution{'s' if count != 1 else ''}"
        else:
            rect = panel.rect(x, y, CELL, CELL, BG, rx=2, stroke=BORDER, stroke_width=.8, **attrs)
            detail = "upcoming day" if item["date"] > data["calendar_end"] else "outside source window"
        node("title", rect).text = f"{item['date']} · {detail}"
        panel.fade(rect, .25 + (item["column"] + item["row"]) * .018, duration=.24)

    panel.text(24, 270, "Outlined squares fall outside the observed dates.", size=10, fill=MUTED)
    # Solve the entire legend from its right edge. Nothing depends on a guessed
    # label width, and the final label ends exactly at the 24px right padding.
    legend_size, legend_font, legend_gap = 12, 11, 4
    word_width = 4 * legend_font * .61
    swatches_width = len(LEVELS) * legend_size + (len(LEVELS) - 1) * legend_gap
    more_right = WIDTH - 24
    swatch_x = more_right - word_width - 12 - swatches_width
    less_x = swatch_x - 12 - word_width
    legend = panel.group(id="contribution-legend")
    panel.text(less_x, 270, "Less", size=legend_font, fill=MUTED, parent=legend)
    for i, colour in enumerate(LEVELS):
        panel.rect(swatch_x + i * (legend_size + legend_gap), 260, legend_size, legend_size,
                   colour, rx=2, parent=legend)
    panel.text(more_right, 270, "More", size=legend_font, fill=MUTED, anchor="end", parent=legend)
    assert less_x >= 24 and more_right <= WIDTH - 24
    assert GRID_X + 52 * STEP + CELL <= WIDTH - 24
    assert GRID_Y + 6 * STEP + CELL < 260

    panel.line(24, 286, WIDTH - 24, 286)
    metrics = [
        (f"{stats['total']:,}", "CONTRIBUTIONS"),
        (f"{stats['active_days']:,}", "ACTIVE DAYS"),
        (f"{stats['longest_streak']}d", "BEST STREAK"),
        (f"{stats['current_streak']}d", "CURRENT STREAK"),
    ]
    spacing = (WIDTH - 48) / len(metrics)
    for i, (value, label) in enumerate(metrics):
        x = 24 + i * spacing
        metric = panel.group()
        panel.text(x, 314, value, size=22, fill=ACCENT, parent=metric)
        panel.text(x, 333, label, size=10.5, fill=MUTED, parent=metric)
        if i:
            panel.line(x - 20, 302, x - 20, 332)
        panel.fade(metric, 1.55 + i * .06, duration=.25)
    panel.save(output)
    return panel


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=ROOT / "data" / "contributions.json")
    parser.add_argument("--output", type=Path, default=ROOT / "contrib-heatmap.svg")
    args = parser.parse_args()
    try:
        data = json.loads(args.input.read_text(encoding="utf-8"))
        render_heatmap(data, args.output)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        parser.exit(1, f"Calendar rendering failed; existing output left unchanged: {exc}\n")
    print(f"Rendered {WIDTH}×{HEIGHT} / 53 weeks → {args.output}")


if __name__ == "__main__":
    main()
