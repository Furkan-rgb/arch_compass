"""Render the raster fallbacks for the tab mark from the same geometry the SVG draws.

Safari does not paint an SVG named by `rel="icon"`, and iOS wants a square bitmap for a
home-screen tile, so `frontend/public/favicon.svg` cannot be the only mark. These two files
are what those two readers get.

Where the SVG is theme-aware and transparent, these are neither: a bitmap cannot carry a
media query, and a single ink-coloured mark on nothing would disappear into whichever tab
strip it did not expect. So the raster fallbacks bring their own ground — canvas behind ink,
the same pairing the page itself uses — and read on any strip, light or dark.

Pillow is asked for here and nowhere else in the project, so it is not a dependency of it.
Run this the once, when the mark's geometry or the ink token changes:

    uv run --with pillow python scripts/generate_favicon_raster.py
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT / "frontend" / "public"

#: The two colours, copied from `--canvas` and `--ink` in `frontend/src/styles.css` — the
#: light pair, because a bitmap has to choose one and the ground it carries is the light one.
CANVAS = (235, 235, 230)
INK = (21, 23, 26)

#: The mark's own coordinate space, which is `favicon.svg`'s viewBox. Every number below is
#: read straight off that file, so the two marks are the same drawing at two resolutions.
VIEWBOX = 32.0
RING_CENTRE = 16.0
RING_RADIUS = 12.5
RING_STROKE = 2.5
NEEDLE = ((21.7, 10.3), (18.1, 18.1), (10.3, 21.7), (13.9, 13.9))

#: Drawn at eight times the asked-for size and reduced, which is the whole of the
#: antialiasing: a 16px ring is a pixel and a quarter wide, and stepping it directly would
#: land it on or off whole pixels rather than between them.
SUPERSAMPLE = 8


def _render(size: int, *, scale: float) -> Image.Image:
    """One square tile: canvas, then the ring and the needle in ink.

    `scale` insets the mark within the tile. The tab icons want the SVG's own margin, which
    is already in the viewBox; the home-screen tile wants more, because iOS crops a rounded
    square out of what it is given and a mark drawn to the edge loses its corners.
    """

    edge = size * SUPERSAMPLE
    unit = edge / VIEWBOX * scale
    offset = (edge - VIEWBOX * unit) / 2

    def place(x: float, y: float) -> tuple[float, float]:
        return (offset + x * unit, offset + y * unit)

    image = Image.new("RGB", (edge, edge), CANVAS)
    draw = ImageDraw.Draw(image)
    # A stroked circle rather than `draw.ellipse(width=…)`, which strokes inside the radius
    # rather than across it: two filled discs, the inner one back in canvas, put the ring
    # where the SVG's `stroke-width` puts it.
    for radius, colour in (
        (RING_RADIUS + RING_STROKE / 2, INK),
        (RING_RADIUS - RING_STROKE / 2, CANVAS),
    ):
        draw.ellipse(
            [
                place(RING_CENTRE - radius, RING_CENTRE - radius),
                place(RING_CENTRE + radius, RING_CENTRE + radius),
            ],
            fill=colour,
        )
    draw.polygon([place(x, y) for x, y in NEEDLE], fill=INK)
    return image.resize((size, size), Image.LANCZOS)


def main() -> None:
    # One file holding 16, 32 and 48, because that is what a browser asking for `favicon.ico`
    # expects to find and it picks the size it wants out of it.
    ico = PUBLIC / "favicon.ico"
    _render(48, scale=1.0).save(ico, format="ICO", sizes=[(16, 16), (32, 32), (48, 48)])
    # 180 is the size iOS asks for and downsamples from; nothing is served by shipping more.
    touch = PUBLIC / "apple-touch-icon.png"
    _render(180, scale=0.72).save(touch, format="PNG")
    for written in (ico, touch):
        print(f"wrote {written.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
