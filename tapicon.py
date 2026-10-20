"""
Draws the Tap to skip icon: a round badge with a "skip to next" glyph.

Used by the tray icon at run time, and by the build to make the .exe icon:
    python tapicon.py icon.ico
"""
import sys

from PIL import Image, ImageDraw

ACTIVE = (41, 98, 255, 255)    # blue
PAUSED = (128, 128, 128, 255)  # gray
WHITE = (255, 255, 255, 255)


def make_icon_image(size=64, paused=False):
    """Return a square RGBA PIL image of the icon."""
    scale = 4                       # draw large, then shrink for smooth edges
    s = size * scale
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.ellipse((0, 0, s - 1, s - 1), fill=PAUSED if paused else ACTIVE)
    # triangle pointing right + a bar = "next"
    tri = [(int(s * 0.28), int(s * 0.27)),
           (int(s * 0.28), int(s * 0.73)),
           (int(s * 0.64), int(s * 0.50))]
    draw.polygon(tri, fill=WHITE)
    draw.rectangle((int(s * 0.68), int(s * 0.27), int(s * 0.76), int(s * 0.73)),
                   fill=WHITE)
    return img.resize((size, size), Image.Resampling.LANCZOS)


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else "icon.ico"
    make_icon_image(256).save(
        out, format="ICO",
        sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (256, 256)])
    print("wrote", out)
