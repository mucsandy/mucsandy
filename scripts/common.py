"""Shared, dependency-free terminal chrome for self-contained SVG images."""

from __future__ import annotations

import os
from pathlib import Path
import tempfile
import xml.etree.ElementTree as ET

SVG_NS = "http://www.w3.org/2000/svg"
ET.register_namespace("", SVG_NS)

ROOT = Path(__file__).resolve().parents[1]
BG = "#0d1117"
BORDER = "#21262d"
FG = "#d3e3dc"
MUTED = "#8b949e"
ACCENT = "#7ee2b8"
LEVELS = ["#161b22", "#0e4429", "#006d32", "#26a641", "#39d353"]
FONT_STACK = "'SFMono-Regular',Consolas,'Liberation Mono',Menlo,Monaco,'Courier New',monospace"


def fmt(value: object) -> str:
    if isinstance(value, float):
        return f"{value:.4f}".rstrip("0").rstrip(".")
    return str(value)


def node(tag: str, parent: ET.Element, **attrs: object) -> ET.Element:
    """Create a namespaced element; Python attribute underscores become hyphens."""
    return ET.SubElement(
        parent,
        f"{{{SVG_NS}}}{tag}",
        {name.replace("_", "-"): fmt(value) for name, value in attrs.items() if value is not None},
    )


def atomic_write(path: Path | str, content: str) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: str | None = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as handle:
            handle.write(content)
            temporary = handle.name
        os.replace(temporary, path)
    finally:
        if temporary is not None and os.path.exists(temporary):
            os.unlink(temporary)


class Panel:
    """A deterministic SVG with a permanent opaque background and fixed text widths.

    Animations have visible base attributes, finite duration, and `both` fill.
    An image viewer without CSS animation support therefore shows the final art.
    STATIC=1 omits animation declarations altogether.
    """

    def __init__(self, width: int, height: int, title: str, description: str, static: bool | None = None):
        self.width, self.height = width, height
        self.static = os.environ.get("STATIC") == "1" if static is None else static
        self.root = ET.Element(f"{{{SVG_NS}}}svg", {
            "width": str(width), "height": str(height),
            "viewBox": f"0 0 {width} {height}", "role": "img",
            "aria-labelledby": "panel-title panel-description",
            "font-family": FONT_STACK,
        })
        node("title", self.root, id="panel-title").text = title
        node("desc", self.root, id="panel-description").text = description
        self._css: list[str] = []
        self._style: ET.Element | None = None
        if not self.static:
            self._style = node("style", self.root)
            self._css.append("@keyframes appear { from { opacity: 0; } to { opacity: 1; } }")
        self.rect(0.5, 0.5, width - 1, height - 1, BG, rx=10, stroke=BORDER, stroke_width=1)
        self.line(0.5, 42, width - 0.5, 42)
        for x, colour in [(19, "#b66b73"), (32, "#c7a56a"), (45, "#75ad88")]:
            node("circle", self.root, cx=x, cy=21, r=3.5, fill=colour)
        self.text(64, 25, title, size=10.5, fill=MUTED)

    def group(self, parent: ET.Element | None = None, **attrs: object) -> ET.Element:
        return node("g", self.root if parent is None else parent, **attrs)

    def rect(self, x: float, y: float, w: float, h: float, fill: str, rx: float = 0,
             parent: ET.Element | None = None, **attrs: object) -> ET.Element:
        return node("rect", self.root if parent is None else parent, x=x, y=y, width=w,
                    height=h, rx=rx, fill=fill, **attrs)

    def line(self, x1: float, y1: float, x2: float, y2: float, stroke: str = BORDER,
             parent: ET.Element | None = None, **attrs: object) -> ET.Element:
        return node("line", self.root if parent is None else parent, x1=x1, y1=y1, x2=x2,
                    y2=y2, stroke=stroke, **attrs)

    def text(self, x: float, y: float, value: str, size: float = 12, fill: str = FG,
             parent: ET.Element | None = None, anchor: str = "start", **attrs: object) -> ET.Element:
        text_width = attrs.pop("text_width", len(value) * size * 0.61)
        element = node("text", self.root if parent is None else parent,
                       x=x, y=y, fill=fill, font_size=size, text_anchor=anchor,
                       textLength=text_width, lengthAdjust="spacingAndGlyphs", **attrs)
        element.text = value
        return element

    def css(self, value: str) -> None:
        if not self.static:
            self._css.append(value)

    def fade(self, element: ET.Element, begin: float, duration: float = 0.28) -> None:
        if self.static:
            return
        element.set("class", (element.get("class", "") + " motion").strip())
        element.set("style", f"animation:appear {fmt(duration)}s ease-out {fmt(begin)}s 1 both")

    def save(self, path: Path | str) -> None:
        if self._style is not None:
            self._style.text = "\n" + "\n".join(self._css) + (
                "\n@media (prefers-reduced-motion: reduce) { "
                ".motion { animation: none !important; opacity: 1 !important; "
                "clip-path: none !important; } }\n"
            )
        ET.indent(self.root, space="  ")
        xml = ET.tostring(self.root, encoding="unicode", xml_declaration=False)
        atomic_write(path, '<?xml version="1.0" encoding="UTF-8"?>\n' + xml + "\n")
