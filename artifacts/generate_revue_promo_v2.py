from __future__ import annotations

import math
from functools import lru_cache
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont


ROOT = Path(__file__).resolve().parent.parent
ARTIFACTS = ROOT / "artifacts"
OUT = ARTIFACTS / "revue_promo_v2.gif"

W, H = 1280, 720
FPS = 12
DURATION = 13
FRAMES = FPS * DURATION

ASSETS = ROOT / "posts" / "static" / "posts" / "images"
WORDMARK = ASSETS / "revue-wordmark-clean.png"
FAVICON = ASSETS / "revue-favicon.png"


BG = (242, 232, 218)
BG2 = (249, 244, 236)
CARD = (255, 252, 247)
INK = (22, 21, 19)
MUTED = (111, 101, 91)
LINE = (227, 211, 193)
ACCENT = (188, 108, 43)
ACCENT_DARK = (126, 65, 25)
SAND = (244, 234, 223)


def ft(size: int, weight: str = "regular") -> ImageFont.FreeTypeFont:
    fonts = {
        "regular": [r"C:\Windows\Fonts\segoeui.ttf", r"C:\Windows\Fonts\arial.ttf"],
        "bold": [r"C:\Windows\Fonts\segoeuib.ttf", r"C:\Windows\Fonts\arialbd.ttf"],
        "italic": [r"C:\Windows\Fonts\segoeuii.ttf", r"C:\Windows\Fonts\georgiai.ttf"],
        "serif_italic": [r"C:\Windows\Fonts\georgiaz.ttf", r"C:\Windows\Fonts\georgiai.ttf"],
    }
    for path in fonts.get(weight, fonts["regular"]):
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def ease(t: float) -> float:
    t = max(0, min(1, t))
    return 1 - pow(1 - t, 3)


def draw_text(draw: ImageDraw.ImageDraw, xy, text: str, size=24, color=INK, weight="regular", anchor=None):
    draw.text(xy, text, font=ft(size, weight), fill=color, anchor=anchor)


def rounded(draw: ImageDraw.ImageDraw, box, r, fill, outline=None, width=1):
    draw.rounded_rectangle(box, radius=r, fill=fill, outline=outline, width=width)


def add_shadow(img: Image.Image, box, radius=28, blur=26, y=14, alpha=40):
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    d.rounded_rectangle((box[0], box[1] + y, box[2], box[3] + y), radius=radius, fill=(82, 52, 30, alpha))
    layer = layer.filter(ImageFilter.GaussianBlur(blur))
    img.alpha_composite(layer)


def gradient_bg() -> Image.Image:
    xs = np.linspace(0, 1, W, dtype=np.float32)[None, :]
    ys = np.linspace(0, 1, H, dtype=np.float32)[:, None]
    t = xs * 0.65 + ys * 0.35
    warm = (20 * t).astype(np.uint8)
    arr = np.zeros((H, W, 4), dtype=np.uint8)
    arr[..., 0] = np.clip(BG[0] + warm, 0, 255)
    arr[..., 1] = np.clip(BG[1] + warm // 2, 0, 255)
    arr[..., 2] = max(BG[2] - 8, 0)
    arr[..., 3] = 255
    img = Image.fromarray(arr, "RGBA")
    glows = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(glows)
    d.ellipse((740, -260, 1450, 450), fill=(205, 135, 72, 52))
    d.ellipse((-250, 300, 530, 910), fill=(255, 248, 238, 120))
    d.ellipse((370, 120, 950, 820), fill=(255, 255, 250, 58))
    img.alpha_composite(glows.filter(ImageFilter.GaussianBlur(80)))
    return img


BG_FRAME = gradient_bg()


def paste_wordmark(img: Image.Image, x: int, y: int, w: int):
    wm = Image.open(WORDMARK).convert("RGBA")
    ratio = w / wm.width
    wm = wm.resize((w, int(wm.height * ratio)), Image.Resampling.LANCZOS)
    img.alpha_composite(wm, (x, y))


def avatar(draw, x, y, letter, size=48):
    draw.ellipse((x, y, x + size, y + size), fill=(18, 17, 16))
    draw_text(draw, (x + size / 2, y + size / 2 - 1), letter, int(size * 0.42), (255, 255, 255), "bold", "mm")


@lru_cache(maxsize=128)
def poster_image(w: int, h: int, title: str, c1: tuple[int, int, int], c2: tuple[int, int, int], mark: str = "") -> Image.Image:
    xs = np.linspace(0, 1, w, dtype=np.float32)[None, :]
    ys = np.linspace(0, 1, h, dtype=np.float32)[:, None]
    t = ys * 0.75 + xs * 0.25
    arr = np.zeros((h, w, 4), dtype=np.uint8)
    for channel in range(3):
        arr[..., channel] = (c1[channel] * (1 - t) + c2[channel] * t).astype(np.uint8)
    arr[..., 3] = 255
    img = Image.fromarray(arr, "RGBA")
    d = ImageDraw.Draw(img)
    for i in range(7):
        cx = int(w * (0.15 + i * 0.13))
        cy = int(h * (0.2 + 0.08 * math.sin(i)))
        d.ellipse((cx - 45, cy - 45, cx + 45, cy + 45), fill=(255, 255, 255, 18))
    if mark:
        draw_text(d, (w - 22, 22), mark, 14, (255, 255, 255), "bold", "ra")
    lines = []
    cur = ""
    for word in title.split():
        test = (cur + " " + word).strip()
        if len(test) > 14 and cur:
            lines.append(cur)
            cur = word
        else:
            cur = test
    if cur:
        lines.append(cur)
    yy = h * 0.47 - len(lines[:3]) * 15
    for line in lines[:3]:
        draw_text(d, (w / 2, yy), line.upper(), 27, (255, 247, 238), "bold", "mm")
        yy += 36
    d.rounded_rectangle((0, 0, w - 1, h - 1), radius=18, outline=(255, 255, 255, 90), width=2)
    return img


POSTERS = [
    ("Succession", "Series", "2018", ((45, 33, 30), (129, 78, 42))),
    ("The Social Network", "Movie", "2010", ((30, 42, 56), (118, 66, 40))),
    ("Brooklyn Nine-Nine", "Series", "2013", ((24, 84, 119), (30, 32, 42))),
    ("Money Trap", "Book", "2024", ((235, 238, 226), (66, 47, 35))),
    ("Maamla Legal Hai", "Series", "2024", ((93, 36, 26), (193, 86, 45))),
    ("Paper Planets", "Book", "2025", ((82, 70, 48), (207, 160, 96))),
]


def paste_poster(img: Image.Image, x: int, y: int, w: int, h: int, title: str, colors, mark=""):
    p = poster_image(w, h, title, colors[0], colors[1], mark)
    mask = Image.new("L", (w, h), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, w, h), radius=18, fill=255)
    img.paste(p, (x, y), mask)


def nav(img: Image.Image, with_search=False, query="", results=False):
    d = ImageDraw.Draw(img)
    paste_wordmark(img, 64, 38, 142)
    if with_search:
        rounded(d, (430, 38, 915, 88), 25, CARD, LINE)
        draw_text(d, (462, 63), "Search", 18, ACCENT_DARK, "bold", "lm")
        draw_text(d, (540, 63), query, 19, INK, "regular", "lm")
        if results:
            add_shadow(img, (430, 104, 915, 286), 24, 22, 8, 32)
            rounded(d, (430, 104, 915, 286), 24, CARD, LINE)
            items = [("Succession", "Series · 2018"), ("The Social Network", "Movie · 2010"), ("Tomorrow, and Tomorrow", "Book · 2022")]
            for i, (title, meta) in enumerate(items):
                yy = 128 + i * 50
                draw_text(d, (462, yy), title, 20, INK, "bold")
                draw_text(d, (462, yy + 25), meta, 16, MUTED)
            rounded(d, (660, 238, 862, 270), 16, SAND, LINE)
            draw_text(d, (761, 254), "Join Revue to see reviews", 15, ACCENT_DARK, "bold", "mm")
    rounded(d, (960, 38, 1075, 88), 25, CARD, LINE)
    draw_text(d, (1017, 63), "Log in", 18, INK, "bold", "mm")
    rounded(d, (1095, 38, 1218, 88), 25, ACCENT)
    draw_text(d, (1156, 63), "Sign up", 18, (255, 255, 255), "bold", "mm")


def scene_open(img: Image.Image, p: float):
    d = ImageDraw.Draw(img)
    query = "succession"[: int(10 * min(1, p * 1.9))]
    nav(img, True, query=query, results=p > 0.48)
    slide = int(34 * (1 - ease(p)))
    draw_text(d, (78, 162 + slide), "Find what to watch,", 64, INK, "bold")
    draw_text(d, (78, 238 + slide), "read, or recommend next.", 64, INK, "bold")
    draw_text(d, (82, 334 + slide), "Through people whose taste you trust.", 26, MUTED)
    rounded(d, (82, 394 + slide, 240, 448 + slide), 27, ACCENT)
    draw_text(d, (161, 421 + slide), "Join Revue", 20, (255, 255, 255), "bold", "mm")
    rounded(d, (260, 394 + slide, 430, 448 + slide), 27, CARD, LINE)
    draw_text(d, (345, 421 + slide), "Explore", 20, INK, "bold", "mm")
    add_shadow(img, (722, 170, 1150, 590), 34, 30, 16, 38)
    rounded(d, (722, 170, 1150, 590), 34, CARD, LINE)
    avatar(d, 765, 220, "M", 60)
    draw_text(d, (842, 222), "Mira Kapoor", 24, INK, "bold")
    draw_text(d, (842, 254), "posted just now", 20, MUTED)
    rounded(d, (1070, 220, 1126, 258), 20, SAND)
    draw_text(d, (1098, 239), "5/5", 18, ACCENT_DARK, "bold", "mm")
    paste_poster(img, 770, 340, 145, 190, "The Glass Harbor", ((77, 51, 35), (172, 108, 56)))
    draw_text(d, (950, 356), "The Glass Harbor", 30, INK, "bold")
    draw_text(d, (950, 400), "Series · IMDb 8.3/10", 20, ACCENT_DARK, "bold")
    draw_text(d, (950, 456), "Slow at first, then", 25, INK, "italic")
    draw_text(d, (950, 492), "impossible to pause.", 25, INK, "italic")


def scene_discover(img: Image.Image, p: float):
    d = ImageDraw.Draw(img)
    nav(img)
    draw_text(d, (74, 126), "Discover shelves that move.", 48, INK, "bold")
    draw_text(d, (76, 184), "Movies, series, and books grouped by mood and momentum.", 24, MUTED)
    rounded(d, (75, 236, 1205, 625), 32, (25, 22, 19), None)
    draw_text(d, (105, 270), "Talk of the town", 28, (255, 250, 244), "bold")
    draw_text(d, (105, 310), "Live discovery without needing a review first.", 20, (196, 184, 172))
    start_x = 105 - int(60 * (1 - ease(p)))
    for i, (title, kind, year, colors) in enumerate(POSTERS):
        x = start_x + i * 175
        y = 360 + int(8 * math.sin(p * math.pi * 2 + i))
        paste_poster(img, x, y, 130, 172, title, colors, f"{15 + i * 5}%")
        draw_text(d, (x, y + 190), title[:18] + ("..." if len(title) > 18 else ""), 19, (255, 250, 244), "bold")
        draw_text(d, (x, y + 218), f"{kind} · {year}", 16, (172, 160, 148), "bold")


def feed_card(img: Image.Image, x, y, user, title, meta, review, colors, score="5/5", kind="Series"):
    d = ImageDraw.Draw(img)
    add_shadow(img, (x, y, x + 760, y + 215), 26, 20, 10, 26)
    rounded(d, (x, y, x + 760, y + 215), 26, CARD, LINE)
    avatar(d, x + 26, y + 24, user[0], 42)
    draw_text(d, (x + 82, y + 24), user, 19, INK, "bold")
    draw_text(d, (x + 82, y + 50), "posted on 8 june 2026", 16, MUTED)
    paste_poster(img, x + 28, y + 84, 105, 105, title, colors)
    draw_text(d, (x + 160, y + 90), title, 24, INK, "bold")
    draw_text(d, (x + 160 + min(330, len(title) * 13), y + 94), kind, 17, MUTED)
    rounded(d, (x + 500, y + 86, x + 600, y + 118), 16, CARD, LINE)
    draw_text(d, (x + 550, y + 102), "IMDb 8.8/10", 15, ACCENT_DARK, "bold", "mm")
    draw_text(d, (x + 160, y + 126), meta, 18, MUTED)
    draw_text(d, (x + 160, y + 162), review, 19, (50, 45, 40), "italic")
    draw_text(d, (x + 160, y + 196), "♥ 1    ◌ 2    Post your review", 16, ACCENT_DARK)
    rounded(d, (x + 705, y + 24, x + 744, y + 57), 16, SAND)
    draw_text(d, (x + 724, y + 41), score, 16, ACCENT_DARK, "bold", "mm")
    draw_text(d, (x + 625, y + 174), "1", 14, ACCENT_DARK, anchor="mm")
    draw_text(d, (x + 625, y + 196), "♥", 28, ACCENT, anchor="mm")
    draw_text(d, (x + 682, y + 196), "▱", 29, INK, anchor="mm")
    draw_text(d, (x + 735, y + 196), "↗", 25, INK, anchor="mm")


def scene_feed(img: Image.Image, p: float):
    d = ImageDraw.Draw(img)
    paste_wordmark(img, 38, 38, 135)
    d.line((34, 110, 260, 110), fill=LINE, width=1)
    rounded(d, (34, 140, 260, 204), 24, CARD, LINE)
    avatar(d, 52, 156, "H", 38)
    draw_text(d, (102, 155), "Harshit More", 17, INK, "bold")
    draw_text(d, (102, 180), "View profile", 16, ACCENT_DARK, "bold")
    draw_text(d, (42, 260), "NAVIGATION", 15, MUTED, "bold")
    rounded(d, (34, 298, 262, 344), 18, SAND)
    draw_text(d, (58, 321), "Home Feed", 18, ACCENT_DARK, "bold", "lm")
    for i, label in enumerate(["Discover", "Friends", "Notifications", "Logout"]):
        draw_text(d, (58, 390 + i * 62), label, 18, INK)

    draw_text(d, (320, 54), "Home feed", 42, INK, "bold")
    draw_text(d, (322, 108), "Reviews from people you follow, recent posts, and quick ways to discover.", 19, MUTED)
    rounded(d, (320, 148, 1045, 210), 23, CARD, LINE)
    labels = ["All types", "Movies", "Books", "TV Shows", "Everyone", "Friends", "New", "Top"]
    xx = 342
    for label in labels:
        active = label in {"All types", "Everyone", "New"}
        w = 88 if len(label) < 8 else 112
        rounded(d, (xx, 164, xx + w, 196), 16, ACCENT if active else CARD, LINE)
        draw_text(d, (xx + w / 2, 180), label, 15, (255, 255, 255) if active else INK, "bold", "mm")
        xx += w + 12
        if label in {"TV Shows", "Friends"}:
            d.line((xx + 2, 164, xx + 2, 196), fill=LINE, width=2)
            xx += 22

    y = 255 - int(24 * ease(p))
    feed_card(img, 320, y, "Harshit More", "Succession", "2018 · Jesse Armstrong", "Might seem slow at first. But the show grows on you.", ((45, 33, 30), (129, 78, 42)))
    feed_card(img, 320, y + 245, "Ankana Boruah", "Brooklyn Nine-Nine", "2013 · Dan Goor", "Good interesting.", ((24, 84, 119), (30, 32, 42)))

    add_shadow(img, (1080, 148, 1238, 388), 24, 22, 10, 30)
    rounded(d, (1080, 148, 1238, 388), 24, CARD, LINE)
    draw_text(d, (1100, 176), "Trending", 22, INK, "bold")
    for i, title in enumerate(["Money Trap", "Made in India", "Tenet"]):
        yy = 220 + i * 52
        draw_text(d, (1100, yy), title, 16, INK, "bold")
        draw_text(d, (1100, yy + 24), f"{5 - i}/5 by Harshit", 14, MUTED)


def scene_finish(img: Image.Image, p: float):
    d = ImageDraw.Draw(img)
    paste_wordmark(img, 505, 86, 270)
    draw_text(d, (640, 225), "Reviews feel better", 62, INK, "bold", "mm")
    draw_text(d, (640, 300), "when they come from people.", 62, INK, "bold", "mm")
    draw_text(d, (640, 390), "Find your next movie, series, or book through taste you trust.", 25, MUTED, anchor="mm")
    rounded(d, (505, 455, 775, 516), 30, ACCENT)
    draw_text(d, (640, 486), "Join Revue", 22, (255, 255, 255), "bold", "mm")
    toast_x = int(1280 - ease(p) * 470)
    rounded(d, (toast_x, 585, toast_x + 420, 660), 30, (29, 26, 23, 230))
    avatar(d, toast_x + 22, 602, "A", 42)
    draw_text(d, (toast_x + 80, 602), "Ankana recommended Succession", 20, (255, 255, 255), "bold")
    draw_text(d, (toast_x + 80, 630), "Series · now trending with friends", 17, (221, 212, 203))


SCENES = [scene_open, scene_discover, scene_feed, scene_finish]


def render():
    frames: list[Image.Image] = []
    scene_len = FRAMES // len(SCENES)
    for i in range(FRAMES):
        img = BG_FRAME.copy()
        scene = min(i // scene_len, len(SCENES) - 1)
        p = (i - scene * scene_len) / scene_len
        SCENES[scene](img, p)
        if p < 0.08 or p > 0.94:
            fade = p / 0.08 if p < 0.08 else (1 - p) / 0.06
            fade = max(0, min(1, fade))
            img.alpha_composite(Image.new("RGBA", img.size, BG + (int((1 - fade) * 255),)))
        frames.append(img.convert("P", palette=Image.Palette.ADAPTIVE, colors=160))
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
