#!/usr/bin/env python3
"""Turn a local portrait into a one-shot, monochrome ASCII terminal SVG.

Background removal, silhouette framing, CLAHE, levels and glyph sampling are
deliberately separate stages. The crop must never depend on graded brightness.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re

import cv2
import numpy as np
from PIL import Image, ImageOps

from common import ACCENT, FG, MUTED, ROOT, Panel, fmt, node

RAMP = " .`:-=+*csS#%@"
WIDTH, HEIGHT = 440, 580
ART_X, ART_Y, ART_WIDTH, ART_HEIGHT = 24.0, 88.0, 392.0, 447.2
COLUMNS, ROWS = 84, 52
FONT_SIZE = 8.15


def remove_background(photo: Path, model: str, cache_dir: Path) -> Image.Image:
    """Cache only local intermediates; the original photograph never enters SVG."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    key = hashlib.sha256(photo.read_bytes() + model.encode() + b"portrait-v1").hexdigest()[:20]
    cache = cache_dir / f"cutout-{key}.png"
    if cache.exists():
        return Image.open(cache).convert("RGBA")

    # Pin inference to local ONNX models. No remote image-processing service.
    if model not in {"u2netp", "u2net", "u2net_human_seg", "isnet-general-use"}:
        raise ValueError("Choose a supported local rembg model.")
    os.environ.setdefault("U2NET_HOME", str(cache_dir / "models"))
    os.environ.setdefault("OMP_NUM_THREADS", "2")
    from rembg import new_session, remove

    with Image.open(photo) as source:
        source = ImageOps.exif_transpose(source).convert("RGB")
        source.thumbnail((1600, 1600), Image.Resampling.LANCZOS)
        session = new_session(model, providers=["CPUExecutionProvider"])
        result = remove(source, session=session).convert("RGBA")
    result.save(cache)
    return result


def silhouette_crop(rgba: Image.Image, head_scale: float = 1.50) -> tuple[Image.Image, dict]:
    """Measure median upper-silhouette width, including dark hair, before grading."""
    alpha = np.asarray(rgba.getchannel("A"))
    binary = (alpha >= 64).astype(np.uint8)
    component_count, labels, stats, _ = cv2.connectedComponentsWithStats(binary, 8)
    if component_count < 2:
        raise ValueError("No person silhouette detected; use a clearly lit single-face photo.")
    largest = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
    silhouette = labels == largest
    ys, _ = np.where(silhouette)
    top, bottom = int(ys.min()), int(ys.max())
    upper_end = top + max(1, round((bottom - top + 1) * 0.60))
    widths, centers = [], []
    for y in range(top, upper_end):
        xs = np.flatnonzero(silhouette[y])
        if xs.size:
            widths.append(int(xs[-1] - xs[0] + 1))
            centers.append(float((xs[0] + xs[-1]) / 2))
    head_width = float(np.median(widths))
    center = float(np.median(centers))
    crop_width = max(1, round(head_width * head_scale))
    crop_height = max(1, round(crop_width * ART_HEIGHT / ART_WIDTH))
    x0 = round(center - crop_width / 2)
    y0 = round(top - head_width * 0.09)
    box = (x0, y0, x0 + crop_width, y0 + crop_height)
    return rgba.crop(box), {
        "silhouette_top": top, "silhouette_bottom": bottom,
        "head_width_median": head_width, "head_center_median": center,
        "crop": list(box), "measurement": "alpha >= 64, upper 60% of largest silhouette",
    }


def grade(crop: Image.Image, black: float, white: float, gamma: float) -> np.ndarray:
    if not 0 <= black < white <= 255 or gamma <= 0:
        raise ValueError("Require 0 <= black < white <= 255 and gamma > 0.")
    rgba = np.asarray(crop)
    gray = cv2.cvtColor(rgba[:, :, :3], cv2.COLOR_RGB2GRAY)
    clahe = cv2.createCLAHE(clipLimit=2.2, tileGridSize=(8, 8))
    local = clahe.apply(gray)
    enhanced = gray.astype(np.float32) * 0.30 + local.astype(np.float32) * 0.70
    # Gamma >1 deepens low values after a hard black point. Clothing becomes space.
    leveled = np.clip((enhanced - black) / (white - black), 0, 1) ** gamma
    leveled *= rgba[:, :, 3].astype(np.float32) / 255.0
    return np.round(leveled * 255).astype(np.uint8)


def ascii_rows(graded: np.ndarray) -> list[str]:
    # Area averaging compensates for each cell's rectangular displayed dimensions.
    samples = cv2.resize(graded, (COLUMNS, ROWS), interpolation=cv2.INTER_AREA)
    indices = np.floor(samples.astype(np.float32) / 255.0 * (len(RAMP) - 1)).astype(int)
    return ["".join(RAMP[index] for index in row) for row in indices]


def render(rows: list[str], output: Path) -> None:
    panel = Panel(WIDTH, HEIGHT, "portrait.sh", "Monochrome ASCII portrait. Rows type once, then remain visible.")
    panel.text(24, 68, "$ render --ascii", size=11, fill=MUTED)
    panel.text(WIDTH - 24, 68, "01", size=10, fill=ACCENT, anchor="end")
    cell_width, row_height = ART_WIDTH / COLUMNS, ART_HEIGHT / ROWS
    defs = node("defs", panel.root) if not panel.static else None
    panel.css(f"@keyframes type-row {{ from {{ width: 0px; }} to {{ width: {fmt(ART_WIDTH)}px; }} }}")
    for r, row in enumerate(rows):
        # No literal spaces are emitted into an ASCII <text>. Separate positioned
        # runs survive XML whitespace collapse and different system mono fonts.
        runs = list(re.finditer(r"[^ ]+", row))
        if not runs:
            continue
        group = panel.group(data_row=r, **{"class": "ascii-row"})
        if not panel.static:
            clip = node("clipPath", defs, id=f"row-{r}", clipPathUnits="userSpaceOnUse")
            clip_rect = panel.rect(ART_X, ART_Y + r * row_height - 2, ART_WIDTH, row_height + 4,
                                   "#ffffff", parent=clip, **{"class": "motion"})
            # Width is final in the base SVG. CSS-only support failure is readable.
            begin, duration = 0.30 + r * 0.048, 0.048
            clip_rect.set("style", f"animation:type-row {fmt(duration)}s steps({COLUMNS},end) {fmt(begin)}s 1 both")
            group.set("clip-path", f"url(#row-{r})")
        baseline = ART_Y + r * row_height + FONT_SIZE
        for run in runs:
            panel.text(ART_X + run.start() * cell_width, baseline, run.group(),
                       size=FONT_SIZE, fill=FG, parent=group,
                       text_width=len(run.group()) * cell_width, **{"class": "ascii-run"})
    panel.text(24, HEIGHT - 21, "portrait · monochrome", size=10, fill=MUTED)
    panel.text(WIDTH - 24, HEIGHT - 21, "84 × 52", size=10, fill=MUTED, anchor="end")
    panel.save(output)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--photo", type=Path, default=ROOT / "assets" / "portrait.jpg")
    parser.add_argument("--output", type=Path, default=ROOT / "ascii-portrait.svg")
    parser.add_argument("--model", default="u2netp", choices=["u2netp", "u2net", "u2net_human_seg", "isnet-general-use"])
    parser.add_argument("--cache-dir", type=Path, default=ROOT / ".cache" / "portrait")
    parser.add_argument("--black", type=float, default=52)
    parser.add_argument("--white", type=float, default=218)
    parser.add_argument("--gamma", type=float, default=1.16)
    parser.add_argument("--head-scale", type=float, default=1.50)
    parser.add_argument("--debug-dir", type=Path, help="Optional local cutout/grade diagnostics; do not commit photographs.")
    args = parser.parse_args()
    if not args.photo.is_file():
        parser.error(f"Photo not found: {args.photo}. Put your photo there or pass --photo PATH.")
    if not 1.1 <= args.head_scale <= 2.5:
        parser.error("--head-scale must be between 1.1 and 2.5")
    cutout = remove_background(args.photo, args.model, args.cache_dir)
    crop, measurement = silhouette_crop(cutout, args.head_scale)
    graded = grade(crop, args.black, args.white, args.gamma)
    rows = ascii_rows(graded)
    render(rows, args.output)
    if args.debug_dir:
        args.debug_dir.mkdir(parents=True, exist_ok=True)
        cutout.save(args.debug_dir / "cutout.png")
        crop.save(args.debug_dir / "crop.png")
        Image.fromarray(graded).save(args.debug_dir / "graded.png")
        (args.debug_dir / "framing.json").write_text(json.dumps(measurement, indent=2) + "\n")
    print(f"Wrote {args.output} ({WIDTH}×{HEIGHT}, {COLUMNS}×{ROWS} characters, median head width {measurement['head_width_median']:.1f}px)")
    # Changing portrait geometry also refreshes the side-by-side README widths.
    if args.output.resolve() == (ROOT / "ascii-portrait.svg").resolve() and (ROOT / "info-card.svg").exists():
        from render_readme import write_readme

        write_readme()


if __name__ == "__main__":
    main()
