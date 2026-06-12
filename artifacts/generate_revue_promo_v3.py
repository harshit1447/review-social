from __future__ import annotations

import math
from functools import lru_cache
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont


ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "artifacts" / "revue_promo_v3.gif"
ASSETS = ROOT / "posts" / "static" / "posts" / "images"
WORDMARK = ASSETS / "revue-wordmark-clean.png"
FAVICON = ASSETS / "revue-favicon.png"

W, H = 1440, 810
FPS = 14
DURATION = 14
FRAMES = FPS * DURATION

CREAM = (243, 235, 224)
PAPER = (255, 252, 247)
INK = (20, 19, 17)
MUTED = (108, 99, 89)
LINE = (224, 209, 192)
ACCENT = (184, 105, 43)
ACCENT_DARK = (122, 63, 25)
SAND = (244, 233, 221)

MOVIES = [
    ("The Glass Harbor", "Series", "2026", "A slow-burning mystery everyone is talking about.", ((36, 44, 52), (154, 103, 68))),
    ("Metro After Dark", "Movie", "2025", "Neon city nights, old friends, impossible choices.", ((23, 28, 34), (141, 66, 78))),
    ("Paper Planets", "Book", "2024", "Tender sci-fi about memory, distance, and home.", ((225, 215, 195), (108, 77, 51))),
    ("Northline", "Series", "2025", "Cold landscapes, warm betrayals, perfect weekend watch.", ((53, 68, 75), (176, 154, 128))),
    ("A Quiet Signal", "Movie", "2024", "Small film. Big aftertaste.", ((37, 35, 31), (182, 126, 64))),
]

PEOPLE = [
    ("Mira Sen", "rated The Glass Harbor 5/5"),
    ("Ayaan Rao", "saved Metro After Dark"),
    ("Tara Malik", "recommended Paper Planets"),
]


def font(size: int, style: str = "regular") -> ImageFont.FreeTypeFont:
    paths = {
        "regular": [r"C:\Windows\Fonts\segoeui.ttf", r"C:\Windows\Fonts\arial.ttf"],
        "bold": [r"C:\Windows\Fonts\segoeuib.ttf", r"C:\Windows\Fonts\arialbd.ttf"],
        "italic": [r"C:\Windows\Fonts\segoeuii.ttf", r"C:\Windows\Fonts\georgiai.ttf"],
    }.get(style, [])
    for path in paths:
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def ease(t: float) -> float:
    t = max(0, min(1, t))
    return t * t * (3 - 2 * t)


def out(t: float) -> float:
    t = max(0, min(1, t))
    return 1 - pow(1 - t, 3)


def tx(d: ImageDraw.ImageDraw, xy, value: str, size=24, fill=INK, style="regular", anchor=None):
    d.text(xy, value, font=font(size, style), fill=fill, anchor=anchor)


def rounded(d: ImageDraw.ImageDraw, box, radius, fill, outline=None, width=1):
    d.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=width)


def shadow(img: Image.Image, box, radius=28, blur=34, y=16, alpha=38):
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    d.rounded_rectangle((box[0], box[1] + y, box[2], box[3] + y), radius=radius, fill=(70, 44, 25, alpha))
    img.alpha_composite(layer.filter(ImageFilter.GaussianBlur(blur)))


def base_bg() -> Image.Image:
    xs = np.linspace(0, 1, W, dtype=np.float32)[None, :]
    ys = np.linspace(0, 1, H, dtype=np.float32)[:, None]
    t = xs * 0.6 + ys * 0.4
    arr = np.zeros((H, W, 4), dtype=np.uint8)
    arr[..., 0] = np.clip(CREAM[0] + 14 * t, 0, 255)
    arr[..., 1] = np.clip(CREAM[1] + 8 * t, 0, 255)
    arr[..., 2] = np.clip(CREAM[2] - 12 * t, 0, 255)
    arr[..., 3] = 255
    img = Image.fromarray(arr, "RGBA")
    glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(glow)
    d.ellipse((820, -260, 1630, 520), fill=(205, 139, 82, 50))
    d.ellipse((-340, 220, 530, 990), fill=(255, 252, 245, 130))
    d.ellipse((380, 180, 1140, 930), fill=(255, 255, 250, 55))
    img.alpha_composite(glow.filter(ImageFilter.GaussianBlur(90)))
    return img


BG = base_bg()


def paste_wordmark(img: Image.Image, x: int, y: int, width: int):
    wm = Image.open(WORDMARK).convert("RGBA")
    ratio = width / wm.width
    wm = wm.resize((width, int(wm.height * ratio)), Image.Resampling.LANCZOS)
    img.alpha_composite(wm, (x, y))


@lru_cache(maxsize=64)
def poster(title: str, w: int, h: int, c1: tuple[int, int, int], c2: tuple[int, int, int]) -> Image.Image:
    xs = np.linspace(0, 1, w, dtype=np.float32)[None, :]
    ys = np.linspace(0, 1, h, dtype=np.float32)[:, None]
    radial = np.sqrt((xs - 0.5) ** 2 + (ys - 0.38) ** 2)
    t = np.clip(ys * 0.75 + xs * 0.25 + radial * 0.26, 0, 1)
    arr = np.zeros((h, w, 4), dtype=np.uint8)
    for ch in range(3):
        arr[..., ch] = (c1[ch] * (1 - t) + c2[ch] * t).astype(np.uint8)
    arr[..., 3] = 255
    img = Image.fromarray(arr, "RGBA")
    d = ImageDraw.Draw(img)
    for i in range(5):
        x = int(w * (0.16 + i * 0.18))
        y = int(h * (0.17 + 0.06 * math.sin(i * 1.7)))
        d.ellipse((x - 38, y - 38, x + 38, y + 38), fill=(255, 255, 255, 16))
    d.rectangle((0, int(h * 0.64), w, h), fill=(0, 0, 0, 55))
    lines = []
    current = ""
    for word in title.split():
        candidate = f"{current} {word}".strip()
        if len(candidate) > 13 and current:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    y0 = int(h * 0.72)
    for line in lines[:3]:
        tx(d, (w / 2, y0), line.upper(), 21 if w < 150 else 27, (250, 243, 234), "bold", "mm")
        y0 += 32
    return img.filter(ImageFilter.UnsharpMask(radius=1, percent=115, threshold=3))


def paste_poster(img: Image.Image, x: int, y: int, w: int, h: int, item):
    p = poster(item[0], w, h, item[4][0], item[4][1])
    mask = Image.new("L", (w, h), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, w, h), radius=22, fill=255)
    img.paste(p, (x, y), mask)


def avatar(d: ImageDraw.ImageDraw, x: int, y: int, letter: str, size=52):
    d.ellipse((x, y, x + size, y + size), fill=(17, 16, 15))
    tx(d, (x + size / 2, y + size / 2 - 1), letter, int(size * 0.42), (255, 255, 255), "bold", "mm")


def nav(img: Image.Image):
    d = ImageDraw.Draw(img)
    paste_wordmark(img, 74, 42, 150)
    rounded(d, (1030, 48, 1135, 96), 24, PAPER, LINE)
    tx(d, (1082, 72), "Log in", 18, INK, "bold", "mm")
    rounded(d, (1155, 48, 1285, 96), 24, ACCENT)
    tx(d, (1220, 72), "Sign up", 18, (255, 255, 255), "bold", "mm")


def search_bar(img: Image.Image, p: float):
    d = ImageDraw.Draw(img)
    query = "glass harbor"[: int(12 * min(1, p * 2.1))]
    shadow(img, (395, 45, 955, 98), 26, 22, 10, 20)
    rounded(d, (395, 45, 955, 98), 26, PAPER, LINE)
    tx(d, (430, 72), "Search", 17, ACCENT_DARK, "bold", "lm")
    tx(d, (512, 72), query, 18, INK, "regular", "lm")
    if p > 0.46:
        reveal = out((p - 0.46) / 0.25)
        h = int(184 * reveal)
        shadow(img, (395, 112, 955, 112 + h), 26, 26, 12, 25)
        rounded(d, (395, 112, 955, 112 + h), 26, PAPER, LINE)
        for i, item in enumerate(MOVIES[:3]):
            yy = 138 + i * 52
            if yy + 35 < 112 + h:
                tx(d, (430, yy), item[0], 19, INK, "bold")
                tx(d, (430, yy + 25), f"{item[1]} · {item[2]} · fictional preview", 15, MUTED)
        if h > 160:
            rounded(d, (655, 258, 910, 292), 17, SAND, LINE)
            tx(d, (782, 275), "Join Revue to see reviews", 15, ACCENT_DARK, "bold", "mm")


def scene_hero(img: Image.Image, p: float):
    d = ImageDraw.Draw(img)
    nav(img)
    search_bar(img, p)
    y = int(36 * (1 - out(p)))
    tx(d, (78, 172 + y), "Find your next", 74, INK, "bold")
    tx(d, (78, 255 + y), "watch through people", 74, INK, "bold")
    tx(d, (78, 338 + y), "you trust.", 74, INK, "bold")
    tx(d, (82, 438 + y), "Search any movie, series, or book. Follow people with similar taste.", 25, MUTED)
    rounded(d, (82, 504 + y, 240, 560 + y), 28, ACCENT)
    tx(d, (161, 532 + y), "Join Revue", 20, (255, 255, 255), "bold", "mm")
    rounded(d, (260, 504 + y, 430, 560 + y), 28, PAPER, LINE)
    tx(d, (345, 532 + y), "Explore", 20, INK, "bold", "mm")

    shadow(img, (748, 170, 1215, 620), 34, 34, 18, 38)
    rounded(d, (748, 170, 1215, 620), 34, PAPER, LINE)
    avatar(d, 788, 216, "M", 62)
    tx(d, (868, 218), "Mira Sen", 25, INK, "bold")
    tx(d, (868, 252), "posted just now", 20, MUTED)
    rounded(d, (1134, 220, 1188, 258), 19, SAND)
    tx(d, (1161, 239), "5/5", 17, ACCENT_DARK, "bold", "mm")
    paste_poster(img, 795, 340, 148, 200, MOVIES[0])
    tx(d, (980, 355), "The Glass Harbor", 31, INK, "bold")
    tx(d, (980, 402), "Series · 2026 · Mystery", 20, MUTED)
    tx(d, (980, 462), "Quiet, tense, and impossible", 25, INK, "italic")
    tx(d, (980, 498), "to stop thinking about.", 25, INK, "italic")


def scene_discovery(img: Image.Image, p: float):
    d = ImageDraw.Draw(img)
    paste_wordmark(img, 74, 42, 150)
    tx(d, (78, 132), "Discovery that feels curated.", 52, INK, "bold")
    tx(d, (80, 196), "Browse fictional shelves, genres, and weekly lists without leaving Revue.", 24, MUTED)
    shadow(img, (80, 260, 1320, 670), 34, 34, 18, 36)
    rounded(d, (80, 260, 1320, 670), 34, PAPER, LINE)
    tx(d, (116, 308), "Weekly top 10", 30, INK, "bold")
    rounded(d, (1078, 300, 1228, 340), 20, SAND, LINE)
    tx(d, (1153, 320), "Movies + Series", 16, ACCENT_DARK, "bold", "mm")
    offset = int(44 * (1 - out(p)))
    for i, item in enumerate(MOVIES):
        x = 118 + i * 225 - offset
        paste_poster(img, x, 378, 165, 220, item)
        tx(d, (x, 620), item[0], 20, INK, "bold")
        tx(d, (x, 648), f"{item[1]} · {item[2]}", 16, MUTED, "bold")


def review_card(img: Image.Image, x: int, y: int, item, person: str, review: str):
    d = ImageDraw.Draw(img)
    shadow(img, (x, y, x + 820, y + 245), 30, 26, 12, 30)
    rounded(d, (x, y, x + 820, y + 245), 30, PAPER, LINE)
    avatar(d, x + 28, y + 28, person[0], 48)
    tx(d, (x + 92, y + 30), person, 21, INK, "bold")
    tx(d, (x + 92, y + 58), "posted today", 17, MUTED)
    rounded(d, (x + 752, y + 30, x + 795, y + 66), 18, SAND)
    tx(d, (x + 773, y + 48), "5/5", 16, ACCENT_DARK, "bold", "mm")
    paste_poster(img, x + 28, y + 104, 118, 118, item)
    tx(d, (x + 172, y + 108), item[0], 27, INK, "bold")
    tx(d, (x + 172 + min(340, len(item[0]) * 14), y + 113), item[1], 18, MUTED)
    rounded(d, (x + 545, y + 105, x + 648, y + 136), 16, PAPER, LINE)
    tx(d, (x + 596, y + 121), "IMDb 8.6/10", 15, ACCENT_DARK, "bold", "mm")
    tx(d, (x + 172, y + 148), f"{item[2]} · fictional creator", 18, MUTED)
    tx(d, (x + 172, y + 184), review, 20, (54, 48, 43), "italic")
    tx(d, (x + 172, y + 219), "♥ 8    ◌ 3    Post your review", 16, ACCENT_DARK)
    tx(d, (x + 656, y + 215), "12", 14, ACCENT_DARK, anchor="mm")
    tx(d, (x + 656, y + 235), "♥", 27, ACCENT, anchor="mm")
    tx(d, (x + 718, y + 235), "▱", 29, INK, anchor="mm")
    tx(d, (x + 780, y + 235), "↗", 27, INK, anchor="mm")


def scene_feed(img: Image.Image, p: float):
    d = ImageDraw.Draw(img)
    paste_wordmark(img, 54, 44, 138)
    d.line((48, 116, 280, 116), fill=LINE, width=1)
    rounded(d, (48, 154, 282, 226), 26, PAPER, LINE)
    avatar(d, 70, 172, "H", 42)
    tx(d, (126, 171), "Harshit More", 18, INK, "bold")
    tx(d, (126, 196), "View profile", 16, ACCENT_DARK, "bold")
    tx(d, (58, 286), "NAVIGATION", 15, MUTED, "bold")
    rounded(d, (48, 326, 285, 376), 18, SAND)
    tx(d, (75, 351), "Home Feed", 18, ACCENT_DARK, "bold", "lm")
    for i, label in enumerate(["Discover", "Friends", "Notifications", "Logout"]):
        tx(d, (75, 425 + i * 64), label, 18, INK)

    tx(d, (345, 58), "Home feed", 44, INK, "bold")
    tx(d, (348, 112), "Fictional reviews from people you follow.", 20, MUTED)
    rounded(d, (345, 154, 1110, 215), 23, PAPER, LINE)
    labels = ["All types", "Movies", "Books", "TV Shows", "Everyone", "Friends", "New", "Top"]
    x = 370
    for label in labels:
        active = label in {"All types", "Everyone", "New"}
        w = 88 if len(label) < 8 else 112
        rounded(d, (x, 170, x + w, 202), 16, ACCENT if active else PAPER, LINE)
        tx(d, (x + w / 2, 186), label, 15, (255, 255, 255) if active else INK, "bold", "mm")
        x += w + 14
        if label in {"TV Shows", "Friends"}:
            d.line((x + 2, 170, x + 2, 202), fill=LINE, width=2)
            x += 24

    slide = int(34 * (1 - out(p)))
    review_card(img, 345, 275 - slide, MOVIES[0], "Mira Sen", "It starts softly and then completely takes over.")
    review_card(img, 345, 545 - slide, MOVIES[1], "Ayaan Rao", "A slick, moody watch with just enough surprise.")

    shadow(img, (1150, 154, 1350, 425), 26, 26, 12, 28)
    rounded(d, (1150, 154, 1350, 425), 26, PAPER, LINE)
    tx(d, (1175, 184), "Revue Quest", 23, INK, "bold")
    tx(d, (1175, 230), "Six questions today.", 17, MUTED)
    rounded(d, (1175, 284, 1325, 326), 21, ACCENT)
    tx(d, (1250, 305), "Play now", 17, (255, 255, 255), "bold", "mm")
    d.line((1175, 350, 1325, 350), fill=LINE, width=1)
    tx(d, (1175, 380), "Friends leaderboard", 16, MUTED, "bold")


def scene_profile(img: Image.Image, p: float):
    d = ImageDraw.Draw(img)
    nav(img)
    shadow(img, (140, 145, 1300, 610), 34, 34, 16, 38)
    rounded(d, (140, 145, 1300, 610), 34, PAPER, LINE)
    cover = Image.new("RGBA", (1080, 210), (0, 0, 0, 0))
    cp = cover.load()
    for y in range(210):
        for x in range(1080):
            t = x / 1080
            cp[x, y] = (
                int(62 * (1 - t) + 182 * t),
                int(42 * (1 - t) + 111 * t),
                int(29 * (1 - t) + 57 * t),
                255,
            )
    cover = cover.filter(ImageFilter.GaussianBlur(0.3))
    img.alpha_composite(cover, (180, 180))
    avatar(d, 224, 340, "T", 108)
    tx(d, (360, 358), "Tara Malik", 45, INK, "bold")
    tx(d, (360, 414), "@tara_reads", 22, MUTED)
    tx(d, (360, 470), "Sharp ratings. Patient notes. Excellent Sunday picks.", 23, MUTED)
    rounded(d, (1065, 420, 1190, 470), 25, ACCENT)
    tx(d, (1128, 445), "Follow", 18, (255, 255, 255), "bold", "mm")
    stats = [("128", "Reviews"), ("3.4k", "Followers"), ("92%", "Taste match")]
    for i, (n, label) in enumerate(stats):
        x = 220 + i * 230
        rounded(d, (x, 510, x + 185, 570), 18, (250, 246, 239), LINE)
        tx(d, (x + 22, 526), n, 26, INK, "bold")
        tx(d, (x + 82, 536), label, 17, MUTED, anchor="lm")

    rounded(d, (735, 510, 1210, 570), 18, (250, 246, 239), LINE)
    tx(d, (765, 530), "Liked lately", 17, MUTED, "bold")
    tx(d, (885, 530), "Northline", 18, INK, "bold")
    tx(d, (885, 555), "Metro After Dark", 18, INK, "bold")


def scene_end(img: Image.Image, p: float):
    d = ImageDraw.Draw(img)
    paste_wordmark(img, 584, 82, 270)
    tx(d, (720, 238), "Find better recommendations", 64, INK, "bold", "mm")
    tx(d, (720, 316), "by following better taste.", 64, INK, "bold", "mm")
    tx(d, (720, 410), "Reviews, lists, likes, and people. All in one quiet place.", 25, MUTED, anchor="mm")
    rounded(d, (586, 482, 854, 545), 31, ACCENT)
    tx(d, (720, 514), "Join Revue", 22, (255, 255, 255), "bold", "mm")
    toast = out(p)
    x = int(1440 - 520 * toast)
    shadow(img, (x, 638, x + 470, 720), 30, 22, 8, 24)
    rounded(d, (x, 638, x + 470, 720), 30, (28, 25, 22, 235))
    avatar(d, x + 28, 658, "M", 44)
    tx(d, (x + 90, 660), "Mira recommended The Glass Harbor", 20, (255, 255, 255), "bold")
    tx(d, (x + 90, 688), "Series · trending with friends", 17, (218, 208, 198))


SCENES = [scene_hero, scene_discovery, scene_feed, scene_profile, scene_end]


def render():
    frames: list[Image.Image] = []
    scene_len = FRAMES // len(SCENES)
    for i in range(FRAMES):
        frame = BG.copy()
        scene_idx = min(i // scene_len, len(SCENES) - 1)
        p = (i - scene_idx * scene_len) / scene_len
        SCENES[scene_idx](frame, p)
        if p < 0.06 or p > 0.95:
            alpha = 1
            if p < 0.06:
                alpha = p / 0.06
            elif p > 0.95:
                alpha = (1 - p) / 0.05
            frame.alpha_composite(Image.new("RGBA", frame.size, CREAM + (int((1 - alpha) * 255),)))
        frames.append(frame.convert("P", palette=Image.Palette.ADAPTIVE, colors=192))
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
