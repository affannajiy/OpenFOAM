#!/usr/bin/env python3
"""
generate_icon.py — Generate the OpenFOAM GUI application icon.

Produces an isometric hexahedral mesh cube icon as SVG, then converts to
PNG at multiple sizes and bundles an .ico file using cairosvg + Pillow.

Run from the deploy directory (Windows CMD or PowerShell):
  python generate_icon.py

If cairosvg is not installed:
  pip install cairosvg           (Windows Python)
  pip install cairosvg --break-system-packages  (WSL Ubuntu)

If Pillow is not installed (needed for .ico):
  pip install Pillow
"""

import math
import os
import sys
import shutil

_HERE       = os.path.dirname(os.path.abspath(__file__))
OUTPUT_SVG  = os.path.join(_HERE, "icon_source.svg")
ICONS_DIR   = os.path.join(_HERE, "icons")
DIST_ICONS  = os.path.join(_HERE, "..", "app", "icons")   # src/app/icons/ (shipped)

BG_COLOUR   = "#1A1A1A"   # matches KS_BLACK / header bar
TOP_COLOUR  = "#E03050"   # slightly brighter red for top face
SIDE_R_CLR  = "#C8102E"   # KS_RED for front-right face
SIDE_L_CLR  = "#A50D25"   # slightly darker for front-left face
OUTLINE_CLR = "#E90029"   # bright red for cube outline

ICON_SIZES  = [16, 32, 48, 64, 128, 256]
N           = 4            # grid divisions per cube edge


# ── Isometric projection ───────────────────────────────────────────────────────

def iso(x, y, z, scale=82, cx=128, cy=140):
    """Map 3D unit-cube coords to 2D isometric screen coordinates (pixels).

    Coordinate convention:
      x-axis: goes toward front-right on screen
      y-axis: goes toward front-left on screen
      z-axis: goes straight up on screen
    """
    sx = (x - y) * scale * math.sqrt(3) / 2
    sy = (x + y) * scale / 2 - z * scale
    return cx + sx, cy + sy


# ── SVG primitives ─────────────────────────────────────────────────────────────

def _line(x1, y1, x2, y2, colour, width=1.2):
    return (f'<line x1="{x1:.2f}" y1="{y1:.2f}" x2="{x2:.2f}" y2="{y2:.2f}" '
            f'stroke="{colour}" stroke-width="{width}" stroke-linecap="round"/>')


def _polygon(pts, fill, opacity=0.18):
    pts_str = " ".join(f"{x:.2f},{y:.2f}" for x, y in pts)
    return (f'<polygon points="{pts_str}" fill="{fill}" '
            f'fill-opacity="{opacity}" stroke="none"/>')


# ── Icon geometry ──────────────────────────────────────────────────────────────

def build_svg() -> str:
    """Return a 256×256 SVG string of the isometric hex-mesh cube icon."""
    elems = []

    # Three visible faces of the unit cube:
    #   Top    (z=1): corners at (0,0,1), (1,0,1), (1,1,1), (0,1,1)
    #   Right  (y=0): corners at (0,0,0), (1,0,0), (1,0,1), (0,0,1)
    #   Left   (x=0): corners at (0,0,0), (0,1,0), (0,1,1), (0,0,1)

    top_pts   = [iso(0,0,1), iso(1,0,1), iso(1,1,1), iso(0,1,1)]
    right_pts = [iso(0,0,0), iso(1,0,0), iso(1,0,1), iso(0,0,1)]
    left_pts  = [iso(0,0,0), iso(0,1,0), iso(0,1,1), iso(0,0,1)]

    # Subtle face fills
    elems.append(_polygon(top_pts,   TOP_COLOUR,   0.20))
    elems.append(_polygon(right_pts, SIDE_R_CLR,   0.15))
    elems.append(_polygon(left_pts,  SIDE_L_CLR,   0.12))

    # Grid lines on top face (z=1): sweep x then y
    for i in range(N + 1):
        t = i / N
        x1, y1 = iso(t, 0, 1);  x2, y2 = iso(t, 1, 1)
        elems.append(_line(x1, y1, x2, y2, TOP_COLOUR, 1.0))
        x1, y1 = iso(0, t, 1);  x2, y2 = iso(1, t, 1)
        elems.append(_line(x1, y1, x2, y2, TOP_COLOUR, 1.0))

    # Grid lines on right face (y=0): sweep x then z
    for i in range(N + 1):
        t = i / N
        x1, y1 = iso(t, 0, 0);  x2, y2 = iso(t, 0, 1)
        elems.append(_line(x1, y1, x2, y2, SIDE_R_CLR, 1.0))
        x1, y1 = iso(0, 0, t);  x2, y2 = iso(1, 0, t)
        elems.append(_line(x1, y1, x2, y2, SIDE_R_CLR, 1.0))

    # Grid lines on left face (x=0): sweep y then z
    for i in range(N + 1):
        t = i / N
        x1, y1 = iso(0, t, 0);  x2, y2 = iso(0, t, 1)
        elems.append(_line(x1, y1, x2, y2, SIDE_L_CLR, 1.0))
        x1, y1 = iso(0, 0, t);  x2, y2 = iso(0, 1, t)
        elems.append(_line(x1, y1, x2, y2, SIDE_L_CLR, 1.0))

    # Visible outline edges (thicker, bright)
    outline_edges = [
        # Top face
        (iso(0,0,1), iso(1,0,1)),
        (iso(1,0,1), iso(1,1,1)),
        (iso(1,1,1), iso(0,1,1)),
        (iso(0,1,1), iso(0,0,1)),
        # Vertical edges
        (iso(0,0,0), iso(0,0,1)),
        (iso(1,0,0), iso(1,0,1)),
        (iso(0,1,0), iso(0,1,1)),
        # Bottom visible edges
        (iso(0,0,0), iso(1,0,0)),
        (iso(0,0,0), iso(0,1,0)),
        (iso(1,0,0), iso(1,1,0)),
        (iso(0,1,0), iso(1,1,0)),
    ]
    for (x1, y1), (x2, y2) in outline_edges:
        elems.append(_line(x1, y1, x2, y2, OUTLINE_CLR, 2.0))

    body = "\n  ".join(elems)
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 256 256" \
width="256" height="256">
  <rect width="256" height="256" rx="28" fill="{BG_COLOUR}"/>
  {body}
</svg>"""


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    """Write icon_source.svg, render every PNG size into both deploy/icons/
    and src/app/icons/, then bundle the multi-size .ico. Exits gracefully
    (SVG only) when cairosvg is not installed."""
    os.makedirs(ICONS_DIR, exist_ok=True)
    os.makedirs(DIST_ICONS, exist_ok=True)

    svg_content = build_svg()
    with open(OUTPUT_SVG, "w", encoding="utf-8") as f:
        f.write(svg_content)
    print(f"SVG written:  {OUTPUT_SVG}")

    try:
        import cairosvg
    except ImportError:
        print("\ncairosvg not found — PNG/ICO generation skipped.")
        print("Install it and re-run:")
        print("  pip install cairosvg              (Windows Python)")
        print("  pip install cairosvg --break-system-packages  (WSL Ubuntu)")
        print(f"\nSVG source: {OUTPUT_SVG}")
        sys.exit(0)

    svg_bytes = svg_content.encode("utf-8")
    for size in ICON_SIZES:
        for dest in (ICONS_DIR, DIST_ICONS):
            out = os.path.join(dest, f"icon_{size}.png")
            cairosvg.svg2png(bytestring=svg_bytes, write_to=out,
                             output_width=size, output_height=size)
            print(f"PNG written:  {out}")

    _build_ico()
    print("\nDone. src/app/icons/ ships with the distribution ZIP.")


def _build_ico():
    """Bundle every PNG size into one Windows .ico (deploy/icons/) and copy it
    to src/app/icons/. Skipped with a hint when Pillow is missing."""
    try:
        from PIL import Image
    except ImportError:
        print("\nPillow not found — .ico skipped.")
        print("Install with: pip install Pillow")
        return

    images = []
    for size in ICON_SIZES:
        p = os.path.join(ICONS_DIR, f"icon_{size}.png")
        images.append(Image.open(p).convert("RGBA"))

    ico_path = os.path.join(ICONS_DIR, "openfoam_ui.ico")
    images[0].save(
        ico_path, format="ICO",
        sizes=[(s, s) for s in ICON_SIZES],
        append_images=images[1:],
    )
    print(f"ICO written:  {ico_path}")
    dist_ico = os.path.join(DIST_ICONS, "openfoam_ui.ico")
    shutil.copy(ico_path, dist_ico)
    print(f"ICO copied:   {dist_ico}")


if __name__ == "__main__":
    main()
