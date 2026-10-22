"""Regression checks for failures that can otherwise be invisible in a README."""
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from validate_svg import SVGValidationError, validate_svg


SAFE = '''<svg xmlns="http://www.w3.org/2000/svg" width="200" height="100" viewBox="0 0 200 100">
<title>Panel</title><desc>Public source https://github.com/users/mucsandy/contributions</desc>
<rect x=".5" y=".5" width="199" height="99" rx="8" fill="#0d1117" stroke="#21262d" stroke-width="1"/>
<text x="20" y="40" font-size="12" font-family="Consolas, monospace" textLength="48" lengthAdjust="spacingAndGlyphs">More</text>
</svg>'''


class SVGValidationTests(unittest.TestCase):
    def check(self, svg=SAFE, *, static=False):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/"fixture.svg"
            path.write_text(svg, encoding="utf-8")
            return validate_svg(path, static=static)

    def fails(self, svg, *, static=False):
        with self.assertRaises(SVGValidationError):
            self.check(svg, static=static)

    def add(self, content):
        return SAFE.replace("</svg>", content+"</svg>")

    def test_safe_panel_and_plain_source_description(self):
        self.assertEqual(self.check().drawn_elements, 2)

    def test_broken_xml(self):
        self.fails(SAFE.replace("</svg>", ""))

    def test_legend_text_off_right_edge(self):
        self.fails(SAFE.replace('x="20"', 'x="170"'))

    def test_stroke_cannot_extend_beyond_panel(self):
        self.fails(self.add('<line x1="10" y1="99" x2="190" y2="99" stroke="#fff" stroke-width="4"/>'))

    def test_inherited_text_style_and_anchor(self):
        self.fails(self.add('<g font-size="12" text-anchor="end"><text x="10" y="80" textLength="50" lengthAdjust="spacingAndGlyphs">Legend</text></g>'))

    def test_script_and_foreign_object(self):
        for content in ('<script>alert(1)</script>', '<foreignObject width="10" height="10"/>'):
            with self.subTest(content=content):
                self.fails(self.add(content))

    def test_event_handler(self):
        self.fails(SAFE.replace('<svg ', '<svg onload="alert(1)" '))

    def test_external_reference_and_webfont(self):
        for content in ('<image href="https://example.org/a.png"/>', '<style>@import "https://example.org/a.css";</style>', '<style>@font-face{font-family:x;src:url(data:font/woff2;base64,AAAA)}</style>'):
            with self.subTest(content=content):
                self.fails(self.add(content))

    def test_remote_paint_reference(self):
        self.fails(SAFE.replace('fill="#0d1117"', 'fill="url(https://example.org/paint.svg#id)"'))

    def test_entity_declaration(self):
        self.fails('<!DOCTYPE svg [<!ENTITY x SYSTEM "file:///etc/passwd">]>'+SAFE)

    def test_css_infinite_or_repeated_animation(self):
        for anim in ('fade 1s infinite', 'fade 1s 2', 'fade 1s;animation-iteration-count:3'):
            with self.subTest(anim=anim):
                self.fails(self.add(f'<style>.motion{{animation:{anim}}}</style>'))

    def test_finite_css_reveal_and_reduced_motion(self):
        css = '<style>@keyframes fade{from{opacity:0}to{opacity:1}}.motion{animation:fade .3s ease .2s 1 both}@media(prefers-reduced-motion:reduce){.motion{animation:none!important;opacity:1!important}}</style>'
        self.assertEqual(self.check(self.add(css)).motion_elements, 1)
        self.fails(self.add(css), static=True)

    def test_smil_infinite_and_out_of_bounds_endpoint(self):
        for animation in ('<animate attributeName="opacity" from="0" to="1" repeatCount="indefinite"/>', '<animate attributeName="width" from="0" to="250" fill="freeze"/>'):
            self.fails(self.add('<rect x="20" y="60" width="40" height="10">'+animation+'</rect>'))

    def test_css_typing_clip_geometry(self):
        css = '<style>@keyframes type-row{from{width:0}to{width:40px}}</style>'
        clip = '<defs><clipPath id="row"><rect x="20" y="60" width="40" height="10" style="animation:type-row .04s steps(8,end) .2s 1 both"/></clipPath></defs>'
        svg = self.add(css+clip)
        self.check(svg)
        self.fails(svg.replace('width:40px', 'width:200px'))
        self.fails(svg, static=True)

    def test_unresolved_stylesheet_geometry_is_rejected(self):
        self.fails(self.add('<style>rect{width:300px}</style>'))
        self.fails(self.add('<style>rect{stroke:#fff}</style>'))

    def test_static_frame_cannot_contain_smil(self):
        svg = self.add('<rect x="20" y="60" width="40" height="10"><animate attributeName="opacity" from="0" to="1" dur="1s" fill="freeze"/></rect>')
        self.check(svg)
        self.fails(svg, static=True)

    def test_unknown_geometry_cannot_bypass_bounds(self):
        self.fails(self.add('<path d="M0 0 L999 999"/>'))
        self.fails(self.add('<g transform="translate(1000 0)"><rect x="1" y="1" width="10" height="10"/></g>'))

    def test_ascii_runs_cannot_contain_spaces(self):
        self.fails(SAFE.replace('>More</text>', '>@@ @</text>').replace('<text ', '<text class="ascii-run" '))

    def test_missing_local_reference(self):
        self.fails(SAFE.replace('textLength="48"', 'clip-path="url(#missing)" textLength="48"'))

    def test_valid_local_clip_path(self):
        svg = self.add('<defs><clipPath id="local"><rect x="10" y="10" width="100" height="60"/></clipPath></defs>')
        svg = svg.replace('textLength="48"', 'clip-path="url(#local)" textLength="48"')
        self.check(svg)


if __name__ == "__main__":
    unittest.main()
