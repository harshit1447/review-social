from __future__ import annotations

import hashlib
import io
import math
import sqlite3
import sys
import urllib.request
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps


ROOT = Path(__file__).resolve().parent.parent
ARTIFACTS = ROOT / "artifacts"
CACHE = ARTIFACTS / "poster_cache"
OUT = ARTIFACTS / "revue_promo_v4.gif"
MP4_OUT = ARTIFACTS / "revue_promo_v4.mp4"
ASSETS = ROOT / "posts" / "static" / "posts" / "images"
WORDMARK = ASSETS / "revue-wordmark-clean.png"

W, H = 1440, 810
FPS = 14
DURATION = 14
FRAMES = FPS * DURATION

CREAM = (244, 235, 224)
PAPER = (255, 252, 247)
INK = (22, 21, 19)
MUTED = (108, 98, 88)
LINE = (225, 209, 191)
ACCENT = (188, 108, 43)
ACCENT_DARK = (121, 61, 24)
SAND = (244, 233, 221)

PEOPLE = ["Mira Sen", "Ayaan Rao", "Tara Malik", "Kabir Mehta", "Naina Bose"]
FICTIONAL_TITLES = [
    "The Glass Harbor",
    "Metro After Dark",
    "Paper Planets",
    "Northline",
    "A Quiet Signal",
    "The Monday Table",
    "Somewhere in Winter",
    "Signal House",
    "The Last Metro",
    "Riverlight",
]


def f(size: int, style: str = "regular") -> ImageFont.FreeTypeFont:
    candidates = {
        "regular": [r"C:\Windows\Fonts\segoeui.ttf", r"C:\Windows\Fonts\arial.ttf"],
        "bold": [r"C:\Windows\Fonts\segoeuib.ttf", r"C:\Windows\Fonts\arialbd.ttf"],
        "italic": [r"C:\Windows\Fonts\segoeuii.ttf", r"C:\Windows\Fonts\georgiai.ttf"],
    }[style]
    for path in candidates:
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def ease(t: float) -> float:
    t = max(0, min(1, t))
    return t * t * (3 - 2 * t)


def out(t: float) -> float:
    t = max(0, min(1, t))
    return 1 - (1 - t) ** 3


def text(d: ImageDraw.ImageDraw, xy, value, size=24, color=INK, style="regular", anchor=None):
    d.text(xy, value, font=f(size, style), fill=color, anchor=anchor)


def rr(d: ImageDraw.ImageDraw, box, r, fill, outline=None, width=1):
    d.rounded_rectangle(box, radius=r, fill=fill, outline=outline, width=width)


def shadow(img: Image.Image, box, r=28, blur=34, y=16, alpha=38):
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    d.rounded_rectangle((box[0], box[1] + y, box[2], box[3],), radius=r, fill=(70, 44, 25, alpha))
    img.alpha_composite(layer.filter(ImageFilter.GaussianBlur(blur)))


def bg() -> Image.Image:
    xs = np.linspace(0, 1, W, dtype=np.float32)[None, :]
    ys = np.linspace(0, 1, H, dtype=np.float32)[:, None]
    t = xs * 0.55 + ys * 0.45
    arr = np.zeros((H, W, 4), dtype=np.uint8)
    arr[..., 0] = np.clip(CREAM[0] + 15 * t, 0, 255)
    arr[..., 1] = np.clip(CREAM[1] + 9 * t, 0, 255)
    arr[..., 2] = np.clip(CREAM[2] - 12 * t, 0, 255)
    arr[..., 3] = 255
    img = Image.fromarray(arr, "RGBA")
    glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(glow)
    d.ellipse((760, -310, 1650, 520), fill=(207, 139, 78, 46))
    d.ellipse((-380, 220, 550, 1000), fill=(255, 253, 248, 120))
    d.ellipse((330, 120, 1120, 900), fill=(255, 255, 250, 46))
    img.alpha_composite(glow.filter(ImageFilter.GaussianBlur(95)))
    return img


BG = bg()


def load_wordmark(width: int) -> Image.Image:
    wm = Image.open(WORDMARK).convert("RGBA")
    ratio = width / wm.width
    return wm.resize((width, int(wm.height * ratio)), Image.Resampling.LANCZOS)


WORDMARK_IMG = load_wordmark(150)


def db_items():
    con = sqlite3.connect(ROOT / "db.sqlite3")
    con.row_factory = sqlite3.Row
    rows = con.execute(
        """
        select title, item_type, release_year, image_url, imdb_rating, book_rating, creator_name
        from posts_item
        where length(coalesce(image_url, '')) > 0
        and image_url not like 'https://example.com/%'
        and lower(item_type) in ('movie', 'series', 'book')
        order by id desc
        limit 18
        """
    ).fetchall()
    return [dict(row) for row in rows]


def cache_path(url: str) -> Path:
    suffix = ".jpg"
    digest = hashlib.sha1(url.encode("utf-8")).hexdigest()
    return CACHE / f"{digest}{suffix}"


def download_posters(items):
    CACHE.mkdir(parents=True, exist_ok=True)
    headers = {"User-Agent": "Mozilla/5.0 RevuePromo/1.0"}
    usable = []
    for item in items:
        url = item["image_url"]
        path = cache_path(url)
        if not path.exists():
            try:
                req = urllib.request.Request(url, headers=headers)
                with urllib.request.urlopen(req, timeout=12) as res:
                    content = res.read()
                im = Image.open(io.BytesIO(content)).convert("RGB")
                if im.width < 80 or im.height < 80:
                    continue
                im.save(path, quality=92)
            except Exception as exc:
                print(f"skip {item['title']}: {exc}")
                continue
        try:
            Image.open(path).verify()
        except Exception:
            path.unlink(missing_ok=True)
            continue
        item["poster_path"] = str(path)
        usable.append(item)
    return usable


def fit_poster(path: str, size: tuple[int, int], mode="cover") -> Image.Image:
    im = Image.open(path).convert("RGBA")
    if mode == "contain":
        canvas = Image.new("RGBA", size, (238, 226, 213, 255))
        thumb = ImageOps.contain(im, size, Image.Resampling.LANCZOS)
        canvas.alpha_composite(thumb, ((size[0] - thumb.width) // 2, (size[1] - thumb.height) // 2))
        im = canvas
    else:
        im = ImageOps.fit(im, size, Image.Resampling.LANCZOS, centering=(0.5, 0.5))
    mask = Image.new("L", size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, size[0], size[1]), radius=20, fill=255)
    out_img = Image.new("RGBA", size, (0, 0, 0, 0))
    out_img.paste(im, (0, 0), mask)
    return out_img


def paste_wordmark(img, x=72, y=42):
    img.alpha_composite(WORDMARK_IMG, (x, y))


def avatar(d, x, y, letter, size=52):
    d.ellipse((x, y, x + size, y + size), fill=(17, 16, 15))
    text(d, (x + size / 2, y + size / 2 - 1), letter, int(size * 0.42), (255, 255, 255), "bold", "mm")


def nav(img):
    d = ImageDraw.Draw(img)
    paste_wordmark(img)
    rr(d, (1030, 48, 1135, 96), 24, PAPER, LINE)
    text(d, (1082, 72), "Log in", 18, INK, "bold", "mm")
    rr(d, (1155, 48, 1288, 96), 24, ACCENT)
    text(d, (1221, 72), "Sign up", 18, (255, 255, 255), "bold", "mm")


def title_short(title: str, n=32) -> str:
    return title if len(title) <= n else title[: n - 1].rstrip() + "…"


def promo_title(item) -> str:
    return item.get("promo_title") or item["title"]


def hero_scene(img, p, items):
    d = ImageDraw.Draw(img)
    nav(img)
    poster_items = items[:5]
    for i, item in enumerate(poster_items):
        x = 760 + i * 72 - int(38 * out(p))
        y = 138 + i * 28
        card = fit_poster(item["poster_path"], (205, 305))
        card = card.filter(ImageFilter.GaussianBlur(1.4 if i > 1 else 0))
        img.alpha_composite(card, (x, y))
    overlay = Image.new("RGBA", (W, H), (244, 235, 224, 0))
    od = ImageDraw.Draw(overlay)
    od.rectangle((700, 80, W, H), fill=(244, 235, 224, 80))
    img.alpha_composite(overlay)

    dy = int(34 * (1 - out(p)))
    text(d, (82, 176 + dy), "Find what to watch,", 72, INK, "bold")
    text(d, (82, 260 + dy), "read, or recommend next.", 72, INK, "bold")
    text(d, (86, 365 + dy), "Through people whose taste you trust.", 26, MUTED)
    rr(d, (86, 430 + dy, 245, 486 + dy), 28, ACCENT)
    text(d, (165, 458 + dy), "Join Revue", 20, (255, 255, 255), "bold", "mm")
    rr(d, (265, 430 + dy, 455, 486 + dy), 28, PAPER, LINE)
    text(d, (360, 458 + dy), "Explore reviews", 20, INK, "bold", "mm")

    shadow(img, (555, 545, 1130, 635), 28, 24, 10, 28)
    rr(d, (555, 545, 1130, 635), 28, (28, 25, 22, 235))
    avatar(d, 585, 565, "M", 48)
    text(d, (650, 570), "Mira Sen just recommended", 20, (255, 255, 255), "bold")
    text(d, (650, 598), title_short(promo_title(items[0]), 45), 18, (226, 216, 205))


def search_scene(img, p, items):
    d = ImageDraw.Draw(img)
    nav(img)
    text(d, (90, 150), "Search feels instant.", 54, INK, "bold")
    text(d, (92, 218), "Find a title first. Review, save, or recommend when you are ready.", 25, MUTED)
    query = "social mystery"[: int(14 * min(1, p * 2.0))]
    shadow(img, (305, 310, 1135, 372), 31, 24, 10, 24)
    rr(d, (305, 310, 1135, 372), 31, PAPER, LINE)
    text(d, (342, 341), "Search", 19, ACCENT_DARK, "bold", "lm")
    text(d, (430, 341), query, 21, INK, "regular", "lm")
    if p > 0.35:
        h = int(250 * out((p - 0.35) / 0.35))
        shadow(img, (305, 390, 1135, 390 + h), 28, 26, 12, 24)
        rr(d, (305, 390, 1135, 390 + h), 28, PAPER, LINE)
        for i, item in enumerate(items[:4]):
            yy = 420 + i * 56
            if yy + 38 < 390 + h:
                thumb = fit_poster(item["poster_path"], (42, 56))
                img.alpha_composite(thumb, (338, yy - 6))
                text(d, (398, yy), title_short(promo_title(item), 46), 20, INK, "bold")
                meta = f"{item['item_type'].title()} · {item.get('release_year') or 'New'}"
                text(d, (398, yy + 26), meta, 16, MUTED)
        if h > 220:
            rr(d, (765, 590, 1080, 626), 18, SAND, LINE)
            text(d, (922, 608), "Join Revue to see reviews and people", 16, ACCENT_DARK, "bold", "mm")


def shelf_scene(img, p, items):
    d = ImageDraw.Draw(img)
    paste_wordmark(img)
    text(d, (84, 138), "Discover by mood, not noise.", 54, INK, "bold")
    text(d, (86, 205), "Weekly shelves built for browsing.", 25, MUTED)
    shadow(img, (82, 270, 1335, 672), 34, 34, 16, 36)
    rr(d, (82, 270, 1335, 672), 34, PAPER, LINE)
    text(d, (118, 316), "Talk of the town", 30, INK, "bold")
    text(d, (118, 356), "Real posters, cleaner motion, fictional social copy.", 20, MUTED)
    x0 = 118 - int(44 * (1 - out(p)))
    for i, item in enumerate(items[:6]):
        x = x0 + i * 198
        im = fit_poster(item["poster_path"], (150, 220))
        img.alpha_composite(im, (x, 410))
        text(d, (x, 652), title_short(promo_title(item), 18), 19, INK, "bold")
        text(d, (x, 680), f"{item['item_type'].title()} · {item.get('release_year') or 'New'}", 15, MUTED, "bold")


def feed_card(img, x, y, item, person, review):
    d = ImageDraw.Draw(img)
    shadow(img, (x, y, x + 830, y + 245), 30, 26, 12, 28)
    rr(d, (x, y, x + 830, y + 245), 30, PAPER, LINE)
    avatar(d, x + 28, y + 26, person[0], 46)
    text(d, (x + 88, y + 28), person, 21, INK, "bold")
    text(d, (x + 88, y + 56), "posted today", 17, MUTED)
    rr(d, (x + 762, y + 28, x + 804, y + 64), 18, SAND)
    text(d, (x + 783, y + 46), "5/5", 16, ACCENT_DARK, "bold", "mm")
    im = fit_poster(item["poster_path"], (118, 145), mode="cover")
    img.alpha_composite(im, (x + 28, y + 92))
    visible_title = promo_title(item)
    text(d, (x + 172, y + 98), title_short(visible_title, 32), 26, INK, "bold")
    text(d, (x + 172, y + 132), f"{item['item_type'].title()} · {item.get('release_year') or 'New'}", 18, MUTED)
    rating = item.get("imdb_rating") or item.get("book_rating")
    if rating:
        rr(d, (x + 540, y + 94, x + 645, y + 126), 16, PAPER, LINE)
        text(d, (x + 592, y + 110), f"IMDb {rating}/10" if item.get("imdb_rating") else f"{rating}", 15, ACCENT_DARK, "bold", "mm")
    text(d, (x + 172, y + 172), review, 20, (54, 48, 43), "italic")
    text(d, (x + 172, y + 212), "♥ 8    ◌ 3    Post your review", 16, ACCENT_DARK)
    text(d, (x + 668, y + 214), "12", 14, ACCENT_DARK, anchor="mm")
    text(d, (x + 668, y + 235), "♥", 27, ACCENT, anchor="mm")
    text(d, (x + 730, y + 235), "▱", 29, INK, anchor="mm")
    text(d, (x + 792, y + 235), "↗", 27, INK, anchor="mm")


def feed_scene(img, p, items):
    d = ImageDraw.Draw(img)
    paste_wordmark(img, 50, 44)
    d.line((44, 116, 275, 116), fill=LINE, width=1)
    rr(d, (44, 150, 276, 222), 26, PAPER, LINE)
    avatar(d, 66, 168, "H", 42)
    text(d, (122, 168), "Harshit More", 18, INK, "bold")
    text(d, (122, 193), "View profile", 16, ACCENT_DARK, "bold")
    text(d, (55, 285), "NAVIGATION", 15, MUTED, "bold")
    rr(d, (44, 324, 280, 374), 18, SAND)
    text(d, (70, 349), "Home Feed", 18, ACCENT_DARK, "bold", "lm")
    for i, label in enumerate(["Discover", "Friends", "Notifications", "Logout"]):
        text(d, (70, 424 + i * 62), label, 18, INK)
    text(d, (350, 62), "Home feed", 44, INK, "bold")
    text(d, (352, 116), "Fictional social activity. Real title artwork.", 20, MUTED)
    rr(d, (350, 158, 1120, 218), 23, PAPER, LINE)
    labels = ["All types", "Movies", "Books", "TV Shows", "Everyone", "Friends", "New", "Top"]
    xx = 374
    for label in labels:
        active = label in {"All types", "Everyone", "New"}
        w = 92 if len(label) < 8 else 116
        rr(d, (xx, 174, xx + w, 204), 15, ACCENT if active else PAPER, LINE)
        text(d, (xx + w / 2, 189), label, 15, (255, 255, 255) if active else INK, "bold", "mm")
        xx += w + 12
        if label in {"TV Shows", "Friends"}:
            d.line((xx + 4, 174, xx + 4, 204), fill=LINE, width=2)
            xx += 24
    slide = int(28 * (1 - out(p)))
    feed_card(img, 350, 282 - slide, items[0], PEOPLE[0], "Exactly the kind of recommendation I wanted.")
    feed_card(img, 350, 545 - slide, items[1], PEOPLE[1], "Stylish, quick, and surprisingly warm.")
    shadow(img, (1160, 158, 1362, 408), 26, 24, 10, 25)
    rr(d, (1160, 158, 1362, 408), 26, PAPER, LINE)
    text(d, (1184, 188), "Revue Quest", 22, INK, "bold")
    text(d, (1184, 238), "Six questions today.", 17, MUTED)
    rr(d, (1184, 292, 1336, 334), 21, ACCENT)
    text(d, (1260, 313), "Play now", 17, (255, 255, 255), "bold", "mm")


def item_scene(img, p, items):
    d = ImageDraw.Draw(img)
    paste_wordmark(img, 58, 42)
    item = items[0]
    shadow(img, (220, 100, 1240, 645), 34, 34, 16, 36)
    rr(d, (220, 100, 1240, 645), 34, PAPER, LINE)
    text(d, (265, 155), f"{item['item_type'].title()} · {item.get('release_year') or 'New'}", 21, MUTED)
    text(d, (265, 215), title_short(promo_title(item), 36), 50, INK, "bold")
    text(d, (265, 285), "One page for details, reactions, and every review from the community.", 24, (55, 49, 43))
    for i, (label, value) in enumerate([
        ("WHY IT MATTERS", "Friends are already talking about it"),
        ("MATCH", "86% with your saved taste"),
        ("RATING", f"IMDb {item.get('imdb_rating') or '8.1'}/10"),
    ]):
        x = 265 + i * 245
        d.line((x, 350, x + 205, 350), fill=LINE, width=2)
        text(d, (x, 378), label, 15, MUTED, "bold")
        text(d, (x, 414), value, 20, INK if i < 2 else ACCENT_DARK, "bold")
    rr(d, (265, 525, 430, 576), 25, ACCENT)
    text(d, (347, 550), "Post your review", 18, (255, 255, 255), "bold", "mm")
    rr(d, (448, 525, 575, 576), 25, PAPER, LINE)
    text(d, (511, 550), "Back to feed", 18, INK, "bold", "mm")
    text(d, (760, 528), "4", 14, ACCENT_DARK, anchor="mm")
    text(d, (760, 552), "♥", 31, ACCENT, anchor="mm")
    text(d, (825, 552), "▱", 31, INK, anchor="mm")
    text(d, (890, 552), "↗", 29, INK, anchor="mm")
    im = fit_poster(item["poster_path"], (245, 365), mode="cover")
    img.alpha_composite(im, (950, 155))


def end_scene(img, p, items):
    d = ImageDraw.Draw(img)
    paste_wordmark(img, 600, 90)
    text(d, (720, 245), "Find better recommendations", 62, INK, "bold", "mm")
    text(d, (720, 320), "through people, not noise.", 62, INK, "bold", "mm")
    text(d, (720, 412), "Movies, series, books, reviews, likes, and lists in one quiet place.", 25, MUTED, anchor="mm")
    rr(d, (590, 492, 850, 555), 31, ACCENT)
    text(d, (720, 524), "Join Revue", 22, (255, 255, 255), "bold", "mm")
    toast_x = int(1440 - 520 * out(p))
    shadow(img, (toast_x, 650, toast_x + 470, 735), 30, 22, 8, 24)
    rr(d, (toast_x, 650, toast_x + 470, 735), 30, (28, 25, 22, 235))
    avatar(d, toast_x + 28, 671, "T", 44)
    text(d, (toast_x + 88, 671), "Tara recommended something new", 20, (255, 255, 255), "bold")
    text(d, (toast_x + 88, 700), "Open Revue to see why", 17, (222, 212, 202))


SCENES = [hero_scene, search_scene, shelf_scene, feed_scene, item_scene, end_scene]


def render():
    raw = db_items()
    items = download_posters(raw)
    if len(items) < 4:
        raise RuntimeError("Need at least 4 usable poster images from the local database.")
    for idx, item in enumerate(items):
        item["promo_title"] = FICTIONAL_TITLES[idx % len(FICTIONAL_TITLES)]
    frames = []
    rgb_frames = []
    scene_len = FRAMES // len(SCENES)
    for i in range(FRAMES):
        frame = BG.copy()
        scene_i = min(i // scene_len, len(SCENES) - 1)
        p = (i - scene_i * scene_len) / scene_len
        SCENES[scene_i](frame, p, items)
        if p < 0.05 or p > 0.95:
            alpha = p / 0.05 if p < 0.05 else (1 - p) / 0.05
            alpha = max(0, min(1, alpha))
            frame.alpha_composite(Image.new("RGBA", frame.size, CREAM + (int((1 - alpha) * 255),)))
        rgb_frames.append(np.asarray(frame.convert("RGB")))
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
    vendor = ARTIFACTS / "vendor"
    if vendor.exists():
        sys.path.insert(0, str(vendor))
    import imageio.v2 as imageio

    with imageio.get_writer(MP4_OUT, fps=FPS, codec="libx264", quality=9, macro_block_size=2) as writer:
        for frame in rgb_frames:
            writer.append_data(frame)
    print(OUT)
    print(MP4_OUT)


if __name__ == "__main__":
    render()
