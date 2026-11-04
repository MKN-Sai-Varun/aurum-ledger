"""Draw synthetic scale and karat-meter images for testing the photo reader.

These are made-up pictures and contain no real data. Run from backend/:
    python scripts/make_sample_images.py
"""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

OUT = Path(__file__).resolve().parents[2] / "samples"
BACKGROUND = (196, 208, 186)
INK = (28, 34, 28)
W, H, T, GAP = 70, 130, 13, 18

SEGMENTS = {
    "0": "abcdef", "1": "bc", "2": "abdeg", "3": "abcdg", "4": "bcfg",
    "5": "acdfg", "6": "acdefg", "7": "abc", "8": "abcdefg", "9": "abcdfg",
}


def draw_digit(draw, x, y, char):
    mid = H // 2
    rects = {
        "a": (T, 0, W - T, T),
        "b": (W - T, T, W, mid),
        "c": (W - T, mid, W, H - T),
        "d": (T, H - T, W - T, H),
        "e": (0, mid, T, H - T),
        "f": (0, T, T, mid),
        "g": (T, mid - T // 2, W - T, mid + T // 2),
    }
    for segment in SEGMENTS[char]:
        x0, y0, x1, y1 = rects[segment]
        draw.rectangle((x + x0, y + y0, x + x1, y + y1), fill=INK)


def scale_display(text):
    width = sum((T + GAP) if ch == "." else (W + GAP) for ch in text) + 80
    image = Image.new("RGB", (width, H + 120), BACKGROUND)
    draw = ImageDraw.Draw(image)
    x, y = 40, 60
    for char in text:
        if char == ".":
            draw.rectangle((x, y + H - T, x + T, y + H), fill=INK)
            x += T + GAP
        else:
            draw_digit(draw, x, y, char)
            x += W + GAP
    return image


def karat_printout(percent):
    image = Image.new("RGB", (520, 360), (250, 250, 246))
    draw = ImageDraw.Draw(image)
    try:
        font = ImageFont.load_default(size=40)
    except TypeError:
        font = ImageFont.load_default()
    lines = ["KARAT METER", "Sample: ring", f"Au   {percent} %", "22K"]
    for index, line in enumerate(lines):
        draw.text((40, 30 + index * 75), line, fill=(20, 20, 20), font=font)
    return image


def main():
    OUT.mkdir(exist_ok=True)
    scale_display("112.450").save(OUT / "scale_112_450.png")
    scale_display("120.000").save(OUT / "scale_120_000.png")
    scale_display("3.300").save(OUT / "scale_3_300.png")
    scale_display("112.450").filter(ImageFilter.GaussianBlur(16)).save(OUT / "scale_blurred.png")
    karat_printout("91.60").save(OUT / "karat_91_60.png")
    print("Wrote 5 sample images to", OUT)


if __name__ == "__main__":
    main()