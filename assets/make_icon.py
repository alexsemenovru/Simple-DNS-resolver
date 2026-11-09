"""Генерирует иконку приложения: скруглённый квадрат с монограммой IP.

Запуск:  python assets/make_icon.py
Нужен Pillow. Результат: assets/icon.png (256) и assets/icon.ico (16…256).
"""
import pathlib

from PIL import Image, ImageDraw, ImageFont

HERE = pathlib.Path(__file__).resolve().parent
SIZE = 1024
RADIUS = 190

TOP = (26, 66, 112)      # #1A4270 — тёмно-синий сверху
BOTTOM = (10, 32, 56)    # #0A2038 — ещё темнее снизу
ACCENT = (79, 195, 247)  # #4FC3F7
FONT_CANDIDATES = [
    r"C:\Windows\Fonts\seguisb.ttf",
    r"C:\Windows\Fonts\segoeuib.ttf",
    r"C:\Windows\Fonts\arialbd.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
]


def gradient(size):
    image = Image.new("RGB", (size, size), TOP)
    draw = ImageDraw.Draw(image)
    for y in range(size):
        ratio = y / max(size - 1, 1)
        color = tuple(
            round(TOP[i] + (BOTTOM[i] - TOP[i]) * ratio) for i in range(3)
        )
        draw.line([(0, y), (size, y)], fill=color)
    return image


def rounded_mask(size, radius):
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, size - 1, size - 1],
                                           radius=radius, fill=255)
    return mask


def load_font(size):
    for path in FONT_CANDIDATES:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    raise SystemExit("Не найден жирный шрифт для иконки")


def build():
    base = gradient(SIZE).convert("RGBA")
    base.putalpha(rounded_mask(SIZE, RADIUS))

    draw = ImageDraw.Draw(base)
    font = load_font(int(SIZE * 0.46))

    text = "IP"
    left, top, right, bottom = draw.textbbox((0, 0), text, font=font)
    width, height = right - left, bottom - top
    position = ((SIZE - width) / 2 - left, (SIZE - height) / 2 - top - SIZE * 0.03)

    # лёгкая тень под буквами — читаемее на светлом фоне
    shadow = Image.new("RGBA", base.size, (0, 0, 0, 0))
    ImageDraw.Draw(shadow).text((position[0], position[1] + SIZE * 0.012), text,
                                font=font, fill=(0, 0, 0, 90))
    base = Image.alpha_composite(base, shadow)

    draw = ImageDraw.Draw(base)
    draw.text(position, text, font=font, fill=(255, 255, 255, 255))

    # маршрут: линия с двумя узлами под монограммой
    y = int(SIZE * 0.735)
    x1, x2 = int(SIZE * 0.30), int(SIZE * 0.70)
    line_width = max(4, int(SIZE * 0.022))
    draw.line([(x1, y), (x2, y)], fill=ACCENT + (255,), width=line_width)
    dot = max(6, int(SIZE * 0.035))
    for cx in (x1, x2):
        draw.ellipse([cx - dot, y - dot, cx + dot, y + dot],
                     fill=ACCENT + (255,))

    return base


def main():
    image = build()
    image.resize((256, 256), Image.LANCZOS).save(HERE / "icon.png")
    image.save(HERE / "icon.ico",
               sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64),
                      (128, 128), (256, 256)])
    print("готово:", HERE / "icon.png", HERE / "icon.ico")


if __name__ == "__main__":
    main()
