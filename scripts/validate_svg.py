#!/usr/bin/env python3
"""Check the small, deliberately constrained SVG dialect used by this project.

No browser or third-party dependency is required, so this check also runs in the
daily heatmap workflow.  Unknown drawing primitives or transforms are errors:
silently skipping their geometry would give a misleading bounds guarantee.
"""
from __future__ import annotations

import argparse
import math
import re
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

SVG_NS = "http://www.w3.org/2000/svg"
ROOT = Path(__file__).resolve().parents[1]
NON_DRAWING = {"svg", "g", "defs", "clipPath", "title", "desc", "metadata", "style", "animate", "set"}
DRAWING = {"rect", "circle", "ellipse", "line", "text"}
ALLOWED = NON_DRAWING | DRAWING
GEOMETRY = {"x", "y", "width", "height", "cx", "cy", "r", "rx", "ry", "x1", "x2", "y1", "y2", "textLength", "font-size", "stroke-width"}
INHERITED = {"fill", "stroke", "stroke-width", "font-size", "font-family", "text-anchor", "dominant-baseline", "letter-spacing"}
URL_RE = re.compile(r"url\(\s*(['\"]?)(.*?)\1\s*\)", re.I | re.S)
NUMBER_RE = re.compile(r"^\s*([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)(?:px)?\s*$")
EPSILON = 0.025


class SVGValidationError(ValueError):
    """The asset violates a self-containment, animation, or bounds constraint."""


def local_name(name: str) -> str:
    return name.rsplit("}", 1)[-1]


def number(value: str | float | int, context: str) -> float:
    match = NUMBER_RE.fullmatch(str(value))
    if not match:
        raise SVGValidationError(f"{context}: expected a scalar number, got {value!r}")
    result = float(match.group(1))
    if not math.isfinite(result):
        raise SVGValidationError(f"{context}: non-finite coordinate")
    return result


def declarations(css: str) -> dict[str, str]:
    return {k.strip(): v.strip() for k, v in re.findall(r"([\w-]+)\s*:\s*([^;{}]+)", css)}


def check_css(css: str, context: str, static: bool) -> list[str]:
    """Inspect CSS without pretending that arbitrary CSS geometry is supported."""
    clean = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    if re.search(r"@(?:import|font-face)\b|(?:javascript|vbscript)\s*:|expression\s*\(|-moz-binding\s*:", clean, re.I):
        raise SVGValidationError(f"{context}: external CSS, webfonts, or executable CSS")
    references = []
    for match in URL_RE.finditer(clean):
        target = match.group(2).strip()
        if not re.fullmatch(r"#[A-Za-z_][\w.:-]*", target):
            raise SVGValidationError(f"{context}: nonlocal CSS reference {target!r}")
        references.append(target[1:])
    if re.search(r"(?:https?:|data:|file:|ftp:|//)", clean, re.I):
        raise SVGValidationError(f"{context}: external or embedded-resource CSS reference")
    if re.search(r"\binfinite\b", clean, re.I):
        raise SVGValidationError(f"{context}: looping animation")
    if static and re.search(r"@(?:-[\w]+-)?keyframes\b|(?:^|[;{\s])(?:-[\w]+-)?animation(?:-[\w]+)?\s*:", clean, re.I):
        raise SVGValidationError(f"{context}: animation is present in a static frame")
    for prop, value in re.findall(r"([\w-]+)\s*:\s*([^;{}]+)", clean):
        if prop.endswith("animation-iteration-count"):
            if any(v.strip() not in {"1", "1.0"} for v in value.split(",")):
                raise SVGValidationError(f"{context}: animation must play exactly once")
        if prop.endswith("animation"):
            stripped = re.sub(r"[\w-]+\([^)]*\)", "", value)
            for token in re.split(r"\s+|,", stripped.strip()):
                if NUMBER_RE.fullmatch(token) and float(token) != 1:
                    raise SVGValidationError(f"{context}: repeated animation in shorthand")
        if prop in {"transform", "translate", "rotate", "scale"} and value.strip() != "none":
            raise SVGValidationError(f"{context}: CSS transform cannot be bounded by this validator")
    return references


def geometric_keyframes(css: str) -> tuple[dict[str, dict[str, list[str]]], str]:
    """Extract numeric geometry endpoints from our simple generated keyframes.

    The unchanged remainder is checked separately so a stylesheet cannot move
    geometry through a selector that the validator does not resolve. Animated
    geometry is supported only on the drawing element's explicit style.
    """
    clean = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    frames: dict[str, dict[str, list[str]]] = {}
    stripped: list[str] = []
    previous = 0
    for match in re.finditer(r"@(?:-[\w]+-)?keyframes\s+([A-Za-z_][\w-]*)\s*\{", clean):
        depth, cursor = 1, match.end()
        while cursor < len(clean) and depth:
            depth += (clean[cursor] == "{") - (clean[cursor] == "}")
            cursor += 1
        if depth:
            raise SVGValidationError("unbalanced CSS keyframe braces")
        stripped.append(clean[previous:match.start()])
        previous = cursor
        geometry: dict[str, list[str]] = {}
        for prop, value in re.findall(r"([\w-]+)\s*:\s*([^;{}]+)", clean[match.end():cursor-1]):
            if prop in GEOMETRY:
                number(value.strip(), f"@keyframes {match.group(1)} {prop}")
                geometry.setdefault(prop, []).append(value.strip())
        if geometry:
            if len(geometry) > 1:
                raise SVGValidationError("simultaneous CSS geometry properties are unsupported")
            if match.group(1) in frames:
                raise SVGValidationError("duplicate geometry keyframe name")
            frames[match.group(1)] = geometry
    stripped.append(clean[previous:])
    remainder = "".join(stripped)
    for prop, _ in re.findall(r"([\w-]+)\s*:\s*([^;{}]+)", remainder):
        if prop in GEOMETRY or prop in {"stroke", "font", "letter-spacing", "dominant-baseline", "text-anchor"}:
            raise SVGValidationError(f"stylesheet changes unbounded geometry ({prop}); use explicit attributes")
    return frames, remainder


@dataclass(frozen=True)
class ValidationResult:
    path: Path
    width: float
    height: float
    drawn_elements: int
    motion_elements: int
    min_content_margin: float


def validate_svg(path: str | Path, *, static: bool = False) -> ValidationResult:
    path = Path(path)
    raw = path.read_text(encoding="utf-8")
    if re.search(r"<!\s*(?:DOCTYPE|ENTITY)\b|<\?xml-stylesheet\b", raw, re.I):
        raise SVGValidationError("DTD, entities, and external XML stylesheets are forbidden")
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as exc:
        raise SVGValidationError(f"invalid XML: {exc}") from exc
    if root.tag != f"{{{SVG_NS}}}svg":
        raise SVGValidationError("root must be an SVG element in the SVG namespace")
    width = number(root.get("width", ""), "root width")
    height = number(root.get("height", ""), "root height")
    if width <= 0 or height <= 0:
        raise SVGValidationError("panel dimensions must be positive")
    view_box = [number(v, "viewBox") for v in re.split(r"[\s,]+", root.get("viewBox", "").strip()) if v]
    if len(view_box) != 4 or any(abs(a-b) > EPSILON for a, b in zip(view_box, (0, 0, width, height))):
        raise SVGValidationError("viewBox must be 0 0 width height")

    ids: set[str] = set()
    local_references: list[str] = []
    css_geometry: dict[str, dict[str, list[str]]] = {}
    style_remainders = []
    for sheet in root.iter(f"{{{SVG_NS}}}style"):
        frames, remainder = geometric_keyframes(sheet.text or "")
        if set(css_geometry) & set(frames):
            raise SVGValidationError("duplicate geometry keyframe name")
        css_geometry.update(frames)
        style_remainders.append(remainder)
    for animation in css_geometry:
        if any(re.search(r"(?<![\w-])" + re.escape(animation) + r"(?![\w-])", text) for text in style_remainders):
            raise SVGValidationError("geometry animation must be declared directly on its drawing element")
    drawn = motion = 0
    min_margin = min(width, height)

    def bounds(attrs: dict[str, str], tag: str, element: ET.Element, context: str) -> tuple[float, float, float, float]:
        def n(key: str, default: str = "0") -> float:
            return number(attrs.get(key, default), f"{context} {key}")

        if tag == "rect":
            x, y, w, h = n("x"), n("y"), n("width"), n("height")
            if min(w, h, n("rx"), n("ry")) < 0:
                raise SVGValidationError(f"{context}: negative rectangle size")
            result = (x, y, x+w, y+h)
        elif tag in {"circle", "ellipse"}:
            cx, cy = n("cx"), n("cy")
            rx, ry = (n("r"), n("r")) if tag == "circle" else (n("rx"), n("ry"))
            if min(rx, ry) < 0:
                raise SVGValidationError(f"{context}: negative radius")
            result = (cx-rx, cy-ry, cx+rx, cy+ry)
        elif tag == "line":
            x1, x2, y1, y2 = n("x1"), n("x2"), n("y1"), n("y2")
            result = (min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2))
        else:
            if list(element):
                # Title/description children do not contribute text glyphs.
                if any(local_name(c.tag) not in {"title", "desc", "animate", "set"} for c in element):
                    raise SVGValidationError(f"{context}: unsupported nested text layout")
            content = element.text or ""
            if "ascii-run" in attrs.get("class", "").split() and any(c.isspace() for c in content):
                raise SVGValidationError(f"{context}: ASCII runs must not contain spaces")
            if content and ("textLength" not in attrs or attrs.get("lengthAdjust") != "spacingAndGlyphs"):
                raise SVGValidationError(f"{context}: text needs explicit textLength and lengthAdjust=spacingAndGlyphs")
            if attrs.get("dominant-baseline", "alphabetic") not in {"auto", "alphabetic"}:
                raise SVGValidationError(f"{context}: unsupported text baseline")
            x, y, length, size = n("x"), n("y"), n("textLength"), n("font-size", "16")
            if length < 0 or size <= 0:
                raise SVGValidationError(f"{context}: invalid text dimensions")
            anchor = attrs.get("text-anchor", "start")
            if anchor not in {"start", "middle", "end"}:
                raise SVGValidationError(f"{context}: unsupported text-anchor {anchor!r}")
            x -= {"start": 0, "middle": length/2, "end": length}[anchor]
            # Explicit textLength fixes horizontal advance across OS font stacks.
            # Conservative bearings and ascent/descender margins cover glyph ink;
            # browser getBBox checks provide an additional visual QA layer.
            bearing = size * .12
            result = (x-bearing, y-size*1.2, x+length+bearing, y+size*.3)
        stroke = n("stroke-width", "1") / 2 if attrs.get("stroke", "none") != "none" else 0
        if stroke < 0:
            raise SVGValidationError(f"{context}: negative stroke width")
        return result[0]-stroke, result[1]-stroke, result[2]+stroke, result[3]+stroke

    def check_bounds(box: tuple[float, float, float, float], context: str, is_chrome: bool = False) -> None:
        nonlocal min_margin
        left, top, right, bottom = box
        if left < -EPSILON or top < -EPSILON or right > width+EPSILON or bottom > height+EPSILON:
            raise SVGValidationError(f"{context}: bounds ({left:.3f}, {top:.3f}, {right:.3f}, {bottom:.3f}) exceed panel (0, 0, {width:g}, {height:g})")
        if not is_chrome:
            min_margin = min(min_margin, left, top, width-right, height-bottom)

    def visit(element: ET.Element, inherited: dict[str, str], in_defs: bool = False) -> None:
        nonlocal drawn, motion
        tag = local_name(element.tag)
        context = f"<{tag}{' #' + element.get('id', '') if element.get('id') else ''}>"
        if not element.tag.startswith(f"{{{SVG_NS}}}") or tag not in ALLOWED:
            raise SVGValidationError(f"{context}: unsupported or unsafe element")
        attrs = {k: v for k, v in inherited.items() if k in INHERITED}
        attrs.update(element.attrib)
        if "style" in attrs:
            local_references.extend(check_css(attrs["style"], context, static))
            attrs.update(declarations(attrs["style"]))
        for key, value in element.attrib.items():
            name = local_name(key)
            if name.lower().startswith("on"):
                raise SVGValidationError(f"{context}: event handlers are forbidden")
            if name == "transform" and value.strip() not in {"", "none"}:
                raise SVGValidationError(f"{context}: transforms require a geometry-aware validator")
            if name in {"href", "src"}:
                if not re.fullmatch(r"#[A-Za-z_][\w.:-]*", value):
                    raise SVGValidationError(f"{context}: nonlocal reference {value!r}")
                local_references.append(value[1:])
            if name != "style" and "url(" in value.lower():
                local_references.extend(check_css(value, context, static))
            if name not in {"style", "id"} and re.search(r"(?:https?:|javascript:|data:|file:|ftp:)", value, re.I):
                raise SVGValidationError(f"{context}: external or embedded-resource attribute")
        if "id" in element.attrib:
            ident = element.attrib["id"]
            if ident in ids:
                raise SVGValidationError(f"{context}: duplicate id")
            ids.add(ident)
        if tag == "style":
            local_references.extend(check_css(element.text or "", context, static))
            if re.search(r"@(?:-[\w]+-)?keyframes\b", element.text or "", re.I):
                motion += 1
        if tag in {"animate", "set"}:
            motion += 1
            if static:
                raise SVGValidationError(f"{context}: SMIL is present in a static frame")
            repeat = element.get("repeatCount", "1")
            if repeat not in {"1", "1.0"} or element.get("repeatDur") is not None:
                raise SVGValidationError(f"{context}: animation must play exactly once")
            if element.get("fill", "freeze") != "freeze":
                raise SVGValidationError(f"{context}: animation must keep its final frame")
            if element.get("attributeName") not in GEOMETRY | {"opacity", "visibility"}:
                raise SVGValidationError(f"{context}: unsupported animation property")
        if tag in DRAWING:
            drawn += 1
            box = bounds(attrs, tag, element, context)
            chrome = tag == "rect" and abs(box[0]) < EPSILON and abs(box[1]) < EPSILON and abs(box[2]-width) < EPSILON and abs(box[3]-height) < EPSILON
            check_bounds(box, context, chrome)
            # Check every independently animated geometry endpoint. Concurrent
            # geometry animations are rejected rather than checking only one at a time.
            animated_geometry = [c for c in element if local_name(c.tag) in {"animate", "set"} and c.get("attributeName") in GEOMETRY]
            if len(animated_geometry) > 1:
                raise SVGValidationError(f"{context}: simultaneous geometry animations are unsupported")
            for animation in animated_geometry:
                prop = animation.get("attributeName", "")
                candidates = animation.get("values", "").split(";") + [animation.get("from", ""), animation.get("to", "")]
                if animation.get("by") is not None or animation.get("additive", "replace") != "replace":
                    raise SVGValidationError(f"{context}: relative/additive geometry animation is unsupported")
                for value in candidates:
                    if value.strip():
                        trial = dict(attrs)
                        trial[prop] = value
                        check_bounds(bounds(trial, tag, element, context), f"{context} animation {prop}={value}", chrome)
            animation_styles = " ".join(attrs.get(key, "") for key in ("animation", "animation-name"))
            matching_css = [name for name in css_geometry if re.search(r"(?<![\w-])" + re.escape(name) + r"(?![\w-])", animation_styles)]
            if len(matching_css) > 1 or (matching_css and animated_geometry):
                raise SVGValidationError(f"{context}: simultaneous geometry animations are unsupported")
            for name in matching_css:
                for prop, values in css_geometry[name].items():
                    for value in values:
                        trial = dict(attrs)
                        trial[prop] = value
                        check_bounds(bounds(trial, tag, element, context), f"{context} CSS {name} {prop}={value}", chrome)
        elif tag not in {"style", "animate", "set"}:
            animation_styles = " ".join(attrs.get(key, "") for key in ("animation", "animation-name"))
            if any(re.search(r"(?<![\w-])" + re.escape(name) + r"(?![\w-])", animation_styles) for name in css_geometry):
                raise SVGValidationError(f"{context}: geometry keyframes must target a drawing element")
        for child in element:
            visit(child, attrs, in_defs or tag in {"defs", "clipPath"})

    visit(root, {})
    for ident in local_references:
        if ident not in ids:
            raise SVGValidationError(f"reference to missing local id #{ident}")
    if drawn == 0:
        raise SVGValidationError("panel contains no drawing elements")
    return ValidationResult(path, width, height, drawn, motion, min_margin)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", type=Path, nargs="*", help="SVG files; defaults to the three profile panels")
    parser.add_argument("--static", action="store_true", help="also reject all animation")
    args = parser.parse_args(argv)
    paths = args.paths or [ROOT/name for name in ("ascii-portrait.svg", "info-card.svg", "contrib-heatmap.svg")]
    failed = False
    for path in paths:
        try:
            result = validate_svg(path, static=args.static)
        except (OSError, SVGValidationError) as exc:
            print(f"FAIL {path.name}: {exc}", file=sys.stderr)
            failed = True
        else:
            print(f"PASS {path.name}: XML, self-contained, one-shot motion, bounds {result.width:g}×{result.height:g}; {result.drawn_elements} drawing elements; minimum content margin {result.min_content_margin:.2f}px")
    return int(failed)


if __name__ == "__main__":
    raise SystemExit(main())
