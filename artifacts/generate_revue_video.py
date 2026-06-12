from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageFilter


ROOT = Path(__file__).resolve().parent
OUT = ROOT / "revue_promo.gif"
W, H = 1280, 720
FPS = 12
DURATION = 12
FRAMES = FPS * DURATION


def font(size: int, bold: bool = False, italic: bool = False) -> ImageFont.FreeTypeFont:
    candidates = []
    if bold:
        candidates += [
            r"C:\Windows\Fonts\segoeuib.ttf",
            r"C:\Windows\Fonts\arialbd.ttf",
        ]
    elif italic:
        candidates += [
            r"C:\Windows\Fonts\segoeuii.ttf",
            r"C:\Windows\Fonts\georgiai.ttf",
        ]
    else:
        candidates += [
            r"C:\Windows\Fonts\segoeui.ttf",
            r"C:\Windows\Fonts\arial.ttf",
        ]
    for path in candidates:
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


FONT = font(28)
BOLD = font(28, bold=True)
SMALL = font(20)
SMALL_BOLD = font(20, bold=True)
SCRIPT = font(72, italic=True)


BG = (242, 232, 218)
CARD = (255, 252, 247)
INK = (23, 22, 20)
MUTED = (112, 101, 91)
ACCENT = (188, 108, 43)
BORDER = (226, 210, 193)
SAND = (242, 231, 219)


def ease(x: float) -> float:
    x = max(0, min(1, x))
    return 1 - (1 - x) ** 3


def lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def rounded(draw: ImageDraw.ImageDraw, box, r: int, fill, outline=None, width=1):
    draw.rounded_rectangle(box, radius=r, fill=fill, outline=outline, width=width)


def shadow(base: Image.Image, box, r=28, blur=24, offset=(0, 12), alpha=45):
    layer = Image.new("RGBA", base.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    shifted = (box[0] + offset[0], box[1] + offset[1], box[2] + offset[0], box[3] + offset[1])
    d.rounded_rectangle(shifted, radius=r, fill=(82, 52, 30, alpha))
    layer = layer.filter(ImageFilter.GaussianBlur(blur))
    base.alpha_composite(layer)


def text(draw, xy, value, size=28, fill=INK, bold=False, italic=False, anchor=None):
    draw.text(xy, value, font=font(size, bold=bold, italic=italic), fill=fill, anchor=anchor)


def poster(base: Image.Image, x: int, y: int, w: int, h: int, title: str, color):
    layer = Image.new("RGBA", (w, h), color + (255,))
    d = ImageDraw.Draw(layer)
    for i in range(0, h, 10):
        shade = int(30 * math.sin(i / 22))
        d.line((0, i, w, i), fill=(max(color[0] + shade, 0), max(color[1] + shade, 0), max(color[2] + shade, 0), 80))
    d.rounded_rectangle((0, 0, w - 1, h - 1), radius=18, outline=(255, 255, 255, 120), width=2)
    words = title.split()
    lines = []
    line = ""
    for word in words:
        test = f"{line} {word}".strip()
        if len(test) > 12 and line:
            lines.append(line)
            line = word
        else:
            line = test
    if line:
        lines.append(line)
    yy = h // 2 - len(lines) * 20
    for line in lines[:4]:
        d.text((w // 2, yy), line.upper(), font=font(28, bold=True), fill=(255, 246, 235), anchor="mm")
        yy += 38
    mask = Image.new("L", (w, h), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, w, h), radius=18, fill=255)
    base.paste(layer, (x, y), mask)


def avatar(draw, x, y, letter, size=58):
    draw.ellipse((x, y, x + size, y + size), fill=(16, 15, 14))
    text(draw, (x + size / 2, y + size / 2 - 2), letter, size=int(size * 0.42), fill=(255, 255, 255), bold=True, anchor="mm")


def draw_nav(draw):
    text(draw, (70, 62), "Revue", size=62, italic=True)
    rounded(draw, (870, 42, 1010, 88), 23, CARD, BORDER)
    text(draw, (940, 65), "Log in", size=20, bold=True, anchor="mm")
    rounded(draw, (1030, 42, 1175, 88), 23, ACCENT)
    text(draw, (1102, 65), "Join Revue", size=20, fill=(255, 255, 255), bold=True, anchor="mm")


def draw_landing(base, p):
    d = ImageDraw.Draw(base)
    draw_nav(d)
    offset = int(60 * (1 - ease(p)))
    text(d, (70, 160 + offset), "Find what to watch,", size=68, bold=True)
    text(d, (70, 238 + offset), "read, or recommend next.", size=68, bold=True)
    text(d, (74, 334 + offset), "Through people who share your taste.", size=28, fill=MUTED)
    rounded(d, (72, 400 + offset, 285, 462 + offset), 31, ACCENT)
    text(d, (178, 430 + offset), "Join Revue", size=23, fill=(255, 255, 255), bold=True, anchor="mm")
    rounded(d, (305, 400 + offset, 505, 462 + offset), 31, CARD, BORDER)
    text(d, (405, 430 + offset), "Explore reviews", size=23, bold=True, anchor="mm")

    shadow(base, (650, 138, 1176, 608), 34)
    rounded(d, (650, 138, 1176, 608), 34, CARD, BORDER)
    avatar(d, 698, 178, "M", 70)
    text(d, (790, 180), "Mira Kapoor", size=28, bold=True)
    text(d, (790, 216), "posted just now", size=22, fill=MUTED)
    rounded(d, (1080, 178, 1142, 222), 22, SAND)
    text(d, (1111, 200), "5/5", size=22, fill=(126, 65, 25), bold=True, anchor="mm")
    poster(base, 700, 292, 170, 230, "The Glass Harbor", (82, 52, 30))
    text(d, (905, 305), "The Glass Harbor", size=36, bold=True)
    text(d, (905, 354), "Series  ·  IMDb 8.3/10", size=24, fill=(126, 65, 25), bold=True)
    text(d, (905, 412), "Slow at first, then suddenly", size=27, fill=INK, italic=True)
    text(d, (905, 452), "impossible to pause.", size=27, fill=INK, italic=True)
    text(d, (905, 535), "♥ 18     ◌ 6     saved by 9", size=23, fill=MUTED)


def draw_feed(base, p):
    d = ImageDraw.Draw(base)
    text(d, (58, 55), "Revue", size=54, italic=True)
    rounded(d, (46, 132, 255, 210), 28, CARD, BORDER)
    avatar(d, 66, 150, "H", 42)
    text(d, (122, 152), "Harshit More", size=20, bold=True)
    text(d, (122, 180), "View profile", size=18, fill=(126, 65, 25), bold=True)
    text(d, (58, 270), "NAVIGATION", size=17, fill=MUTED, bold=True)
    rounded(d, (42, 306, 270, 360), 22, SAND)
    text(d, (68, 321), "Home Feed", size=22, fill=(126, 65, 25), bold=True)
    text(d, (68, 395), "Discover", size=22)
    text(d, (68, 465), "Friends", size=22)
    text(d, (68, 535), "Notifications", size=22)

    text(d, (340, 55), "Home feed", size=52, bold=True)
    text(d, (342, 118), "Reviews from people you follow, recent posts, and quick ways to discover what is worth your time.", size=22, fill=MUTED)
    rounded(d, (342, 162, 980, 230), 24, CARD, BORDER)
    for i, label in enumerate(["All types", "Movies", "Books", "TV Shows", "Everyone", "Friends", "New", "Top"]):
        x = 368 + i * 74 + (26 if i > 3 else 0)
        w = 84 if len(label) > 6 else 72
        active = label in {"All types", "Everyone", "New"}
        rounded(d, (x, 178, x + w, 214), 18, ACCENT if active else CARD, BORDER)
        text(d, (x + w / 2, 196), label, size=16, fill=(255, 255, 255) if active else INK, bold=True, anchor="mm")

    y = 278 - int(35 * ease(p))
    for idx, (name, title, meta, review, color) in enumerate([
        ("Harshit More", "Succession", "2018 · Jesse Armstrong", "Might seem slow at first. But the show grows on you.", (71, 48, 38)),
        ("Ankana Boruah", "Brooklyn Nine-Nine", "2013 · Dan Goor", "Good interesting", (32, 90, 120)),
    ]):
        yy = y + idx * 205
        shadow(base, (340, yy, 1015, yy + 165), 24, 18, (0, 8), 28)
        rounded(d, (340, yy, 1015, yy + 165), 24, CARD, BORDER)
        avatar(d, 365, yy + 24, name[0], 42)
        text(d, (420, yy + 24), name, size=20, bold=True)
        text(d, (420, yy + 50), "posted on 6 june 2026", size=17, fill=MUTED)
        poster(base, 365, yy + 82, 92, 118, title, color)
        text(d, (485, yy + 83), title, size=25, bold=True)
        text(d, (485, yy + 117), meta, size=20, fill=MUTED)
        text(d, (485, yy + 150), review, size=20, italic=True)
        rounded(d, (938, yy + 24, 982, yy + 58), 17, SAND)
        text(d, (960, yy + 41), "5/5", size=17, fill=(126, 65, 25), bold=True, anchor="mm")
        text(d, (850, yy + 126), "1", size=15, fill=(126, 65, 25), anchor="mm")
        text(d, (850, yy + 148), "♥", size=28, fill=ACCENT, anchor="mm")
        text(d, (910, yy + 148), "▱", size=30, fill=INK, anchor="mm")
        text(d, (970, yy + 148), "↗", size=28, fill=INK, anchor="mm")

    shadow(base, (1045, 160, 1230, 365), 24)
    rounded(d, (1045, 160, 1230, 365), 24, CARD, BORDER)
    text(d, (1070, 185), "Daily Quiz", size=23, bold=True)
    rounded(d, (1160, 178, 1210, 212), 17, SAND)
    text(d, (1185, 195), "6/6", size=16, fill=(126, 65, 25), bold=True, anchor="mm")
    text(d, (1070, 240), "Revue Quest", size=20, bold=True)
    text(d, (1070, 285), "Six questions today.", size=18, fill=MUTED)
    rounded(d, (1070, 318, 1208, 350), 16, ACCENT)
    text(d, (1139, 334), "Play now", size=16, fill=(255, 255, 255), bold=True, anchor="mm")


def draw_item(base, p):
    d = ImageDraw.Draw(base)
    text(d, (58, 55), "Revue", size=54, italic=True)
    shadow(base, (210, 80, 1185, 590), 30)
    rounded(d, (210, 80, 1185, 590), 30, CARD, BORDER)
    text(d, (250, 130), "Series · 2018", size=21, fill=MUTED)
    text(d, (250, 185), "Succession", size=50, bold=True)
    text(d, (250, 255), "The Roy family controls the biggest media company in the world.", size=24, fill=(48, 43, 38))
    text(d, (250, 292), "Then power shifts, loyalties crack, and every conversation turns into a battle.", size=24, fill=(48, 43, 38))
    for i, (k, v) in enumerate([("DIRECTOR", "Jesse Armstrong"), ("CAST", "Nicholas Braun, Brian Cox"), ("YEAR", "2018"), ("RATINGS", "IMDb 8.8/10")]):
        x = 250 + i * 210
        d.line((x, 340, x + 170, 340), fill=BORDER, width=2)
        text(d, (x, 365), k, size=16, fill=MUTED, bold=True)
        if k == "RATINGS":
            rounded(d, (x, 395, x + 125, 430), 17, CARD, BORDER)
            text(d, (x + 62, 413), v, size=17, fill=(126, 65, 25), bold=True, anchor="mm")
        else:
            text(d, (x, 400), v, size=20)
    poster(base, 940, 110, 190, 330, "Succession", (54, 36, 26))
    rounded(d, (250, 500, 395, 545), 23, ACCENT)
    text(d, (322, 522), "Post your review", size=18, fill=(255, 255, 255), bold=True, anchor="mm")
    rounded(d, (410, 500, 525, 545), 23, CARD, BORDER)
    text(d, (467, 522), "Back to feed", size=18, bold=True, anchor="mm")
    text(d, (790, 486), "1", size=16, fill=(126, 65, 25), anchor="mm")
    text(d, (790, 515), "♥", size=34, fill=ACCENT, anchor="mm")
    text(d, (850, 515), "▱", size=35, fill=INK, anchor="mm")
    text(d, (910, 515), "↗", size=32, fill=INK, anchor="mm")


def draw_recommend(base, p):
    d = ImageDraw.Draw(base)
    draw_nav(d)
    text(d, (80, 150), "Recommendations that", size=60, bold=True)
    text(d, (80, 220), "start with your taste.", size=60, bold=True)
    text(d, (84, 310), "Follow people, save lists, and see why a title matches you.", size=27, fill=MUTED)
    shadow(base, (120, 395, 555, 605), 30)
    rounded(d, (120, 395, 555, 605), 30, CARD, BORDER)
    text(d, (155, 430), "Because you liked", size=22, fill=MUTED)
    text(d, (155, 465), "Sherlock + Peaky Blinders", size=30, bold=True)
    poster(base, 385, 430, 110, 145, "Industry", (35, 54, 68))
    text(d, (155, 525), "Try Industry", size=32, bold=True)
    text(d, (155, 565), "Sharp dialogue, ambition, pressure.", size=21, fill=MUTED)

    shadow(base, (680, 150, 1120, 585), 32)
    rounded(d, (680, 150, 1120, 585), 32, CARD, BORDER)
    text(d, (720, 190), "Latest from your circle", size=28, bold=True)
    for i, (letter, line) in enumerate([
        ("A", "Ankana reviewed Brooklyn Nine-Nine"),
        ("R", "Rishi saved Money Trap"),
        ("M", "Mira recommended The Glass Harbor"),
    ]):
        yy = 250 + i * 95
        avatar(d, 720, yy, letter, 52)
        text(d, (790, yy + 2), line, size=22, bold=True)
        text(d, (790, yy + 34), "posted today", size=19, fill=MUTED)
        d.line((720, yy + 76, 1080, yy + 76), fill=BORDER, width=1)
    rounded(d, (720, 520, 880, 560), 20, ACCENT)
    text(d, (800, 540), "Open Revue", size=18, fill=(255, 255, 255), bold=True, anchor="mm")


def background() -> Image.Image:
    img = Image.new("RGBA", (W, H), BG + (255,))
    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(overlay)
    for i in range(14):
        x = int(W * (i / 13))
        color = (255, 245, 234, 36) if i % 2 else (201, 145, 89, 20)
        d.ellipse((x - 260, -180, x + 270, 360), fill=color)
    overlay = overlay.filter(ImageFilter.GaussianBlur(75))
    img.alpha_composite(overlay)
    return img


def render():
    frames: list[Image.Image] = []
    scenes = [draw_landing, draw_feed, draw_item, draw_recommend]
    scene_len = FRAMES // len(scenes)
    for i in range(FRAMES):
        base = background()
        scene_idx = min(i // scene_len, len(scenes) - 1)
        p = (i - scene_idx * scene_len) / scene_len
        scenes[scene_idx](base, p)
        fade = 1
        if p < 0.08:
            fade = p / 0.08
        elif p > 0.92:
            fade = (1 - p) / 0.08
        if fade < 1:
            black = Image.new("RGBA", base.size, (242, 232, 218, int((1 - fade) * 255)))
            base.alpha_composite(black)
        frames.append(base.convert("P", palette=Image.Palette.ADAPTIVE, colors=128))
    frames[0].save(
        OUT,
        save_all=True,
        append_images=frames[1:],
        duration=int(1000 / FPS),
        loop=0,
        optimize=True,
        disposal=2,
    )
    print(OUT)


if __name__ == "__main__":
    render()
