#!/usr/bin/env python3
"""Render the personal neofetch panel; no network or GitHub statistics.

Run with STATIC=1 to emit the fully visible final frame. Details are kept in
profile.json. Rendering the default card also recalculates README image sizes.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from common import ACCENT, BORDER, FG, MUTED, Panel

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / "profile.json"
DEFAULT_OUTPUT = ROOT / "info-card.svg"
FONT_SIZE = 18
ADVANCE = FONT_SIZE * 0.61
ROW_STEP = 31
FIRST_ROW_Y = 170
MARGIN = 30


def load_profile(path: Path) -> tuple[str, list[tuple[str, str]]]:
    """Validate plain-text fields, then join multi-item values with U+00B7."""
    data = json.loads(path.read_text(encoding="utf-8"))
    username = data.get("username", "")
    if not isinstance(username, str) or not re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})", username):
        raise ValueError("profile.json needs a valid GitHub username")
    entries = data.get("rows")
    if not isinstance(entries, list) or not entries:
        raise ValueError("profile.json needs a nonempty rows list")
    rows = []
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError("Each profile row must be an object")
        label = entry.get("label", "")
        if not isinstance(label, str):
            raise ValueError("A row label must be text")
        if "items" in entry:
            items = entry["items"]
            if not isinstance(items, list) or not items or any(not isinstance(item, str) or not item.strip() for item in items):
                raise ValueError("Row items must be a nonempty list of nonempty strings")
            value = " · ".join(item.strip() for item in items)
        else:
            value = entry.get("value", "")
            if not isinstance(value, str) or not value.strip():
                raise ValueError("A row value must be nonempty text")
        if any(ord(char) < 32 for char in label + value):
            raise ValueError("Profile rows must not contain control characters or newlines")
        rows.append((label.strip(), value.strip()))
    return username, rows


def render_card(config: Path, output: Path) -> tuple[int, int]:
    username, rows = load_profile(config)
    label_width = max((len(label) for label, _ in rows), default=0) * ADVANCE
    value_x = MARGIN + label_width + 30
    longest_value = max(len(value) for _, value in rows) * ADVANCE
    heading_width = len(f"{username}@github") * 22 * 0.61
    width = max(620, int(max(value_x + longest_value, MARGIN + heading_width) + MARGIN + 1))
    height = FIRST_ROW_Y + (len(rows) - 1) * ROW_STEP + 61
    description = f"{username}: " + "; ".join(f"{key}: {value}" if key else value for key, value in rows)
    panel = Panel(width, height, "profile / neofetch", description)
    panel.text(MARGIN, 77, "$ neofetch --profile", size=13, fill=MUTED)
    heading = panel.group()
    panel.text(MARGIN, 114, f"{username}@github", size=22, fill=ACCENT, parent=heading)
    panel.fade(heading, 0.12, 0.3)
    panel.line(MARGIN, 134, width - MARGIN, 134, stroke=BORDER)
    for index, (label, value) in enumerate(rows):
        y = FIRST_ROW_Y + index * ROW_STEP
        row = panel.group()
        if label:
            panel.text(MARGIN, y, label, size=FONT_SIZE, fill=ACCENT, parent=row)
        panel.text(value_x, y, value, size=FONT_SIZE, fill=FG, parent=row)
        panel.fade(row, 0.26 + index * 0.105, 0.32)
    # A restrained terminal palette is decoration, not statistics.
    palette_y = height - 32
    palette = panel.group()
    for index, color in enumerate(("#21262d", "#354b44", "#48675b", "#5b8d77", "#6fb698", "#7ee2b8")):
        panel.rect(MARGIN + index * 21, palette_y, 16, 8, fill=color, rx=1, parent=palette)
    panel.fade(palette, 0.36 + len(rows) * 0.105, 0.3)
    panel.save(output)
    return width, height


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--no-readme", action="store_true", help="Do not regenerate README after a default card render")
    args = parser.parse_args()
    width, height = render_card(args.config, args.output)
    print(f"Wrote {args.output} ({width} x {height})")
    if not args.no_readme and args.output.resolve() == DEFAULT_OUTPUT.resolve():
        if (ROOT / "ascii-portrait.svg").is_file():
            from render_readme import write_readme

            write_readme(config=args.config)
        else:
            print("Render the portrait, then run scripts/render_readme.py to calculate panel widths.")


if __name__ == "__main__":
    main()
