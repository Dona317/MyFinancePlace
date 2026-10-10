"""
The app's icon (program, tray, notifications, installer), drawn here so it can be remade: the accent colour of the
app and the rising chart of the sidebar logo.

    python -m desktop.make_icon      # writes desktop/assets/icon.png and icon.ico
"""
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
    points = [(0.20, 0.70), (0.40, 0.50), (0.55, 0.62), (0.80, 0.32)]
    width = big // 13
    pen.line([(x * big, y * big) for x, y in points], fill="white", width=width, joint="curve")
    tip = (0.80 * big, 0.32 * big)
    arrow = big * 0.14
    pen.polygon([tip, (tip[0] - arrow, tip[1] + arrow * 0.15), (tip[0] - arrow * 0.15, tip[1] + arrow)], fill="white")
    for x, y in points[:-1]:
        radius = width * 0.62
        pen.ellipse((x * big - radius, y * big - radius, x * big + radius, y * big + radius), fill="white")
    return image.resize((size, size), Image.LANCZOS)


def main() -> None:
    ASSETS.mkdir(exist_ok=True)
    image = draw()
    image.save(ASSETS / "icon.png")
    image.save(ASSETS / "icon.ico", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    print(f"icon → {ASSETS}")


if __name__ == "__main__":
    main()
