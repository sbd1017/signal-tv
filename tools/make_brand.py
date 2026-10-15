"""The new interface's `tv.` brand: header wordmark and app/browser icons, from Jost (SIL Open Font
Licence, the interface's own fallback display font), so they are the same on every device and
free to use anywhere. Run on a development machine (needs fontTools + Pillow), then commit the output:

    python3 tools/make_brand.py

Writes (all owned by web-next/, nothing from Classic's web/):
    web-next/pwa/icon.svg               browser tab (vector)
    web-next/pwa/icon-192.png, icon-512.png       the tile: rounded, transparent outside
    web-next/pwa/icon-maskable-512.png  full-bleed square, the mark inside the safe zone (Android)
    web-next/pwa/apple-touch-icon.png   180 px, full-bleed and opaque (iOS rounds it)
    web-next/index.html                 the header mark, between <!-- brand:mark --> markers

The mark: "tv" in Jost 800, tracked slightly tight, with the tally dot as its full stop. In the
header the dot is the live light: red, and glowing while something is on air (app.css .mark-dot).
"""
from __future__ import annotations

import re
from pathlib import Path

from fontTools.pens.basePen import BasePen
from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen
from fontTools.ttLib import TTFont
from fontTools.varLib.instancer import instantiateVariableFont
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
FONT = next((ROOT / "web-next/static/fonts").glob("jost-*-latin.woff2"))
PWA = ROOT / "web-next/pwa"
INK, RED, TILE = "#f2efe8", "#ff4b3a", "#111316"
TEXT, WEIGHT, TRACK = "tv", 800, -0.02


def jost():
    return instantiateVariableFont(TTFont(FONT), {"wght": WEIGHT})


F = jost()
GS, CMAP, HMTX, UPM = F.getGlyphSet(), F.getBestCmap(), F["hmtx"], F["head"].unitsPerEm


def layout(size):
    """[(glyph name, x offset)] for TEXT at `size` px, and the advance width."""
    out, x = [], 0.0
    for ch in TEXT:
        g = CMAP[ord(ch)]
        out.append((g, x))
        x += HMTX[g][0] * size / UPM + TRACK * size
    return out, x - TRACK * size


def bounds(size):
    b = BoundsPen(GS)
    for g, x in layout(size)[0]:
        GS[g].draw(TransformPen(b, (size / UPM, 0, 0, -size / UPM, x, 0)))
    return b.bounds                                       # y down: (xmin, top, xmax, bottom)


def xheight(size):
    b = BoundsPen(GS)
    GS[CMAP[ord("x")]].draw(TransformPen(b, (size / UPM, 0, 0, -size / UPM, 0, 0)))
    return -b.bounds[1]


def geometry(size):
    """Glyph placement + the dot, relative to the text's own box (x from its left, y from its top)."""
    xmin, top, xmax, bottom = bounds(size)
    r = xheight(size) * 0.27
    dot_cx = xmax + size * 0.07 + r
    return {"xmin": xmin, "top": top, "bottom": bottom, "width": dot_cx + r - xmin, "r": r,
            "dot": (dot_cx - xmin, -top - r)}       # dot sits on the baseline, like a full stop


def path_d(size, dx, dy):
    pen = SVGPathPen(GS)
    for g, x in layout(size)[0]:
        GS[g].draw(TransformPen(pen, (size / UPM, 0, 0, -size / UPM, x + dx, dy)))
    return pen.getCommands()


class Polygons(BasePen):
    """Flattens outlines into polygons for Pillow (these glyphs have no counters)."""

    def __init__(self, gs, steps=16):
        super().__init__(gs)
        self.polys, self.cur, self.steps = [], [], steps

    def _moveTo(self, p):
        self.cur = [p]

    def _lineTo(self, p):
        self.cur.append(p)

    def _curveToOne(self, p1, p2, p3):
        p0 = self.cur[-1]
        for i in range(1, self.steps + 1):
            t = i / self.steps
            mt = 1 - t
            self.cur.append((mt ** 3 * p0[0] + 3 * mt * mt * t * p1[0] + 3 * mt * t * t * p2[0] + t ** 3 * p3[0],
                             mt ** 3 * p0[1] + 3 * mt * mt * t * p1[1] + 3 * mt * t * t * p2[1] + t ** 3 * p3[1]))

    def _qCurveToOne(self, p1, p2):
        p0 = self.cur[-1]
        for i in range(1, self.steps + 1):
            t = i / self.steps
            mt = 1 - t
            self.cur.append((mt * mt * p0[0] + 2 * mt * t * p1[0] + t * t * p2[0], mt * mt * p0[1] + 2 * mt * t * p1[1] + t * t * p2[1]))

    def _closePath(self):
        if len(self.cur) > 2:
            self.polys.append(self.cur)
        self.cur = []

    _endPath = _closePath


def tile_png(px, rounded, scale):
    """The tile at px x px: the mark centred, `scale` = its width as a share of the tile."""
    ss = 4                                                 # supersample, then downscale: smooth edges
    n = px * ss
    im = Image.new("RGBA", (n, n), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    if rounded:
        d.rounded_rectangle((0, 0, n - 1, n - 1), radius=n * 0.22, fill=TILE)
    else:
        d.rectangle((0, 0, n, n), fill=TILE)
    size = 100.0
    g = geometry(size)
    k = n * scale / g["width"]
    size *= k
    g = geometry(size)
    ox = (n - g["width"]) / 2 - g["xmin"]
    oy = (n - (g["bottom"] - g["top"])) / 2 - g["top"]
    pen = Polygons(GS)
    for gl, x in layout(size)[0]:
        GS[gl].draw(TransformPen(pen, (size / UPM, 0, 0, -size / UPM, x + ox, oy)))
    for poly in pen.polys:
        d.polygon(poly, fill=INK)
    cx, cy = g["dot"][0] + g["xmin"] + ox, g["dot"][1] + g["top"] + oy
    d.ellipse((cx - g["r"], cy - g["r"], cx + g["r"], cy + g["r"]), fill=RED)
    return im.resize((px, px), Image.LANCZOS)


def tile_svg():
    n, scale, size = 512, 0.62, 100.0
    g = geometry(size)
    size *= n * scale / g["width"]
    g = geometry(size)
    ox = (n - g["width"]) / 2 - g["xmin"]
    oy = (n - (g["bottom"] - g["top"])) / 2 - g["top"]
    cx, cy = g["dot"][0] + g["xmin"] + ox, g["dot"][1] + g["top"] + oy
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {n} {n}"><rect width="{n}" height="{n}" rx="{n * 0.22:.0f}" fill="{TILE}"/>'
            f'<path d="{path_d(size, ox, oy)}" fill="{INK}"/><circle cx="{cx:.1f}" cy="{cy:.1f}" r="{g["r"]:.1f}" fill="{RED}"/></svg>\n')


def header_svg():
    """The wordmark for the top bar: inline, ink in currentColor, the dot a separate element (the tally)."""
    size = 100.0
    g = geometry(size)
    pad = g["r"] * 1.6                                     # room for the dot's glow
    w, h = g["width"] + pad, (g["bottom"] - g["top"]) + pad / 2
    d = path_d(size, -g["xmin"], -g["top"])
    cx, cy = g["dot"]
    return (f'<svg class="mark-svg" viewBox="0 0 {w:.1f} {h:.1f}" aria-hidden="true" focusable="false">'
            f'<path d="{d}" fill="currentColor"/>'
            f'<circle class="mark-dot" id="tally" cx="{cx:.1f}" cy="{cy:.1f}" r="{g["r"]:.1f}"/></svg>')


def main():
    PWA.mkdir(exist_ok=True)
    (PWA / "icon.svg").write_text(tile_svg())
    tile_png(192, True, 0.62).save(PWA / "icon-192.png", optimize=True)
    tile_png(512, True, 0.62).save(PWA / "icon-512.png", optimize=True)
    tile_png(512, False, 0.46).save(PWA / "icon-maskable-512.png", optimize=True)   # inside the 80 % safe zone
    tile_png(180, False, 0.56).convert("RGB").save(PWA / "apple-touch-icon.png", optimize=True)
    index = ROOT / "web-next/index.html"
    html = index.read_text()
    new = re.sub(r"(<!-- brand:mark -->).*?(<!-- /brand:mark -->)", lambda m: m[1] + header_svg() + m[2], html, flags=re.S)
    if new == html and "<!-- brand:mark -->" not in html:
        raise SystemExit("index.html has no <!-- brand:mark --> markers")
    index.write_text(new)
    print("brand written:", ", ".join(p.name for p in sorted(PWA.glob("icon*"))), "+ apple-touch-icon.png + header mark")


if __name__ == "__main__":
    main()
