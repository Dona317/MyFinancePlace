"""
The app's icon (program, tray, notifications, installer), drawn here so it can be remade: the accent colour of the
app and the rising chart of the sidebar logo.

    python -m desktop.make_icon      # writes desktop/assets/icon.png and icon.ico
"""
import math
from pathlib import Path

from PIL import Image, ImageDraw

ASSETS = Path(__file__).resolve().parent / "assets"
ACCENT = (200, 80, 15, 255)   # --clr-primary
SIZE = 256


def draw(size: int = SIZE) -> Image.Image:
    scale = 4  # drawn larger, then reduced: smooth edges
    big = size * scale
    image = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    pen = ImageDraw.Draw(image)
    pen.rounded_rectangle((0, 0, big - 1, big - 1), radius=big // 5, fill=ACCENT)
    points = [(x * big, y * big) for x, y in ((0.18, 0.72), (0.40, 0.50), (0.56, 0.62), (0.84, 0.30))]
    width = big // 13

    # the arrowhead points the same way as the last segment, symmetric around it
    (x1, y1), (x2, y2) = points[-2], points[-1]
    length = math.hypot(x2 - x1, y2 - y1)
    dx, dy = (x2 - x1) / length, (y2 - y1) / length      # along the segment
    nx, ny = -dy, dx                                      # across it
    head, half = big * 0.20, big * 0.13                   # arrowhead length and half width
    base = (x2 - dx * head, y2 - dy * head)
    pen.line(points[:-1] + [base], fill="white", width=width, joint="curve")
    pen.polygon([(x2, y2), (base[0] + nx * half, base[1] + ny * half), (base[0] - nx * half, base[1] - ny * half)],
                fill="white")
    for x, y in points[:-1]:  # round joints and start
        radius = width * 0.62
        pen.ellipse((x - radius, y - radius, x + radius, y + radius), fill="white")
    return image.resize((size, size), Image.LANCZOS)


def main() -> None:
    ASSETS.mkdir(exist_ok=True)
    image = draw()
    image.save(ASSETS / "icon.png")
    image.save(ASSETS / "icon.ico", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    print(f"icon → {ASSETS}")


if __name__ == "__main__":
    main()
