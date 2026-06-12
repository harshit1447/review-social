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
VENDOR = ARTIFACTS / "vendor"
if VENDOR.exists():
    sys.path.insert(0, str(VENDOR))

ASSETS = ROOT / "posts" / "static" / "posts" / "images"
WORDMARK = ASSETS / "revue-wordmark-clean.png"
MP4_OUT = ARTIFACTS / "revue_promo_v5.mp4"
GIF_OUT = ARTIFACTS / "revue_promo_v5_preview.gif"
THUMB_OUT = ARTIFACTS / "revue_promo_v5_thumb.png"

W, H = 1440, 810
FPS = 18
DURATION = 15
FRAMES = FPS * DURATION

CREAM = (244, 235, 224)
PAPER = (255, 252, 247)
INK = (22, 21, 19)
MUTED = (108, 98, 88)
SOFT = (248, 241, 232)
LINE = (224, 210, 194)
ACCENT = (188, 108, 43)
ACCENT_DARK = (118, 63, 28)

PEOPLE = ["Mira Sen", "Ayaan Rao", "Tara Malik", "Kabir Mehta", "Naina Bose"]
TITLES = [
    "The Glass Harbor",
    "Metro After Dark",
    "Paper Planets",
    "Northline",
    "A Quiet Signal",
    "The Monday Table",
    "Riverlight",
    "A House of Weather",
]


def font(size: int, style: str = "regular") -> ImageFont.FreeTypeFont:
    candidates = {
        "regular": [r"C:\Windows\Fonts\segoeui.ttf", r"C:\Windows\Fonts\arial.ttf"],
        "bold": [r"C:\Windows\Fonts\segoeuib.ttf", r"C:\Windows\Fonts\arialbd.ttf"],
        "italic": [r"C:\Windows\Fonts\segoeuii.ttf", r"C:\Windows\Fonts\georgiai.ttf"],
    }[style]
    for path in candidates:
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def clamp(v: float, a=0.0, b=1.0) -> float:
    return max(a, min(b, v))


def ease(t: float) -> float:
    t = clamp(t)
    return t * t * (3 - 2 * t)


def ease_out(t: float) -> float:
    t = clamp(t)
    return 1 - (1 - t) ** 3


def local_t(global_t: float, start: float, end: float) -> float:
    return clamp((global_t - start) / (end - start))


def draw_text(
    d: ImageDraw.ImageDraw,
    xy: tuple[float, float],
    value: str,
    size=24,
    color=INK,
    style="regular",
    anchor=None,
    spacing=6,
):
    d.multiline_text(xy, value, font=font(size, style), fill=color, anchor=anchor, spacing=spacing)


def rounded(d: ImageDraw.ImageDraw, box, radius: int, fill, outline=None, width=1):
    d.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=width)


def add_shadow(img: Image.Image, box, radius=28, blur=34, y=14, alpha=34):
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    d.rounded_rectangle((box[0], box[1] + y, box[2], box[3] + y), radius=radius, fill=(74, 47, 25, alpha))
    img.alpha_composite(layer.filter(ImageFilter.GaussianBlur(blur)))


def background() -> Image.Image:
    xs = np.linspace(0, 1, W, dtype=np.float32)[None, :]
    ys = np.linspace(0, 1, H, dtype=np.float32)[:, None]
    t = xs * 0.6 + ys * 0.35
    arr = np.zeros((H, W, 4), dtype=np.uint8)
    arr[..., 0] = np.clip(CREAM[0] + 14 * t, 0, 255)
    arr[..., 1] = np.clip(CREAM[1] + 8 * t, 0, 255)
    arr[..., 2] = np.clip(CREAM[2] - 8 * t, 0, 255)
    arr[..., 3] = 255
    img = Image.fromarray(arr, "RGBA")
    glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(glow)
    d.ellipse((740, -260, 1600, 470), fill=(204, 137, 78, 42))
    d.ellipse((-420, 260, 480, 980), fill=(255, 255, 250, 100))
    img.alpha_composite(glow.filter(ImageFilter.GaussianBlur(90)))
    return img


BG = background()


def wordmark(width=150) -> Image.Image:
    wm = Image.open(WORDMARK).convert("RGBA")
    ratio = width / wm.width
    return wm.resize((width, int(wm.height * ratio)), Image.Resampling.LANCZOS)


WORDMARK_IMG = wordmark()


def db_items() -> list[dict]:
    con = sqlite3.connect(ROOT / "db.sqlite3")
    con.row_factory = sqlite3.Row
    rows = con.execute(
        """
        select title, item_type, release_year, image_url, imdb_rating, creator_name
        from posts_item
        where length(coalesce(image_url, '')) > 0
        and image_url not like 'https://example.com/%'
        and lower(item_type) in ('movie', 'series', 'book')
        order by id desc
        limit 24
        """
    ).fetchall()
    con.close()
    return [dict(row) for row in rows]


def cache_path(url: str) -> Path:
    return CACHE / f"{hashlib.sha1(url.encode('utf-8')).hexdigest()}.jpg"


def load_items() -> list[dict]:
    CACHE.mkdir(parents=True, exist_ok=True)
    items = []
    headers = {"User-Agent": "Mozilla/5.0 RevuePromo/1.0"}
    for item in db_items():
        path = cache_path(item["image_url"])
        if not path.exists():
            try:
                req = urllib.request.Request(item["image_url"], headers=headers)
                with urllib.request.urlopen(req, timeout=10) as res:
                    raw = res.read()
                im = Image.open(io.BytesIO(raw)).convert("RGB")
                if im.width < 80 or im.height < 80:
                    continue
                im.save(path, quality=92)
            except Exception as exc:
                print(f"Skipping poster: {item['title']} ({exc})")
                continue
        try:
            Image.open(path).verify()
        except Exception:
            path.unlink(missing_ok=True)
            continue
        item["poster_path"] = str(path)
        items.append(item)
    return items


def poster(path: str, size: tuple[int, int], radius=22, contain=False) -> Image.Image:
    im = Image.open(path).convert("RGBA")
    if contain:
        base = Image.new("RGBA", size, (237, 224, 208, 255))
        thumb = ImageOps.contain(im, size, Image.Resampling.LANCZOS)
        base.alpha_composite(thumb, ((size[0] - thumb.width) // 2, (size[1] - thumb.height) // 2))
        im = base
    else:
        im = ImageOps.fit(im, size, Image.Resampling.LANCZOS, centering=(0.5, 0.5))
    mask = Image.new("L", size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, size[0], size[1]), radius=radius, fill=255)
    out = Image.new("RGBA", size, (0, 0, 0, 0))
    out.paste(im, (0, 0), mask)
    return out


def avatar(d: ImageDraw.ImageDraw, x: int, y: int, letter: str, size=54):
    d.ellipse((x, y, x + size, y + size), fill=(17, 16, 15))
    draw_text(d, (x + size / 2, y + size / 2 - 2), letter, int(size * 0.42), (255, 255, 255), "bold", "mm")


def pill(d, x, y, text_value, active=False, w=None):
    tw = d.textbbox((0, 0), text_value, font=font(18, "bold"))[2]
    width = w or tw + 34
    fill = ACCENT if active else PAPER
    color = (255, 255, 255) if active else INK
    rounded(d, (x, y, x + width, y + 48), 24, fill, LINE)
    draw_text(d, (x + width / 2, y + 24), text_value, 18, color, "bold", "mm")


def nav(img):
    d = ImageDraw.Draw(img)
    img.alpha_composite(WORDMARK_IMG, (74, 42))
    rounded(d, (1042, 44, 1150, 94), 25, PAPER, LINE)
    draw_text(d, (1096, 69), "Log in", 18, INK, "bold", "mm")
    rounded(d, (1170, 44, 1302, 94), 25, ACCENT)
    draw_text(d, (1236, 69), "Join Revue", 18, (255, 255, 255), "bold", "mm")


def draw_poster_card(img, item, x, y, w=190, h=280, label="The Glass Harbor", meta="Movie"):
    d = ImageDraw.Draw(img)
    add_shadow(img, (x, y, x + w, y + h + 70), 24, 22, 8, 22)
    img.alpha_composite(poster(item["poster_path"], (w, h), 18, contain=item.get("item_type") == "book"), (x, y))
    draw_text(d, (x, y + h + 18), label, 21, INK, "bold")
    draw_text(d, (x, y + h + 48), f"{meta} - picked by taste", 15, MUTED, "bold")


def scene_hero(img, p, items):
    d = ImageDraw.Draw(img)
    nav(img)
    slide = int(28 * (1 - ease_out(p)))
    draw_text(d, (88, 180 + slide), "Find what to\nwatch next\nthrough people\nyou trust.", 72, INK, "bold", spacing=7)
    draw_text(
        d,
        (92, 542 + slide // 2),
        "Follow taste, not algorithms.\nReviews, lists, and recommendations from people who get it.",
        25,
        MUTED,
        "regular",
        spacing=8,
    )
    rounded(d, (92, 660, 250, 716), 28, ACCENT)
    draw_text(d, (171, 688), "Join Revue", 19, (255, 255, 255), "bold", "mm")
    rounded(d, (268, 660, 410, 716), 28, PAPER, LINE)
    draw_text(d, (339, 688), "Explore", 19, INK, "bold", "mm")

    panel = (660, 136, 1328, 704)
    add_shadow(img, panel, 42, 40, 20, 32)
    rounded(d, panel, 42, PAPER, LINE)
    avatar(d, 718, 186, "M", 62)
    draw_text(d, (800, 192), "Mira Sen", 24, INK, "bold")
    draw_text(d, (800, 226), "posted just now", 19, MUTED)
    rounded(d, (1204, 186, 1264, 232), 23, SOFT)
    draw_text(d, (1234, 209), "5/5", 18, ACCENT_DARK, "bold", "mm")

    img.alpha_composite(poster(items[0]["poster_path"], (210, 310), 24), (730, 330))
    draw_text(d, (978, 354), "The Glass Harbor", 34, INK, "bold")
    rounded(d, (978, 406, 1116, 450), 22, SOFT)
    draw_text(d, (1047, 428), "Series", 18, MUTED, "regular", "mm")
    rounded(d, (1132, 406, 1276, 450), 22, SOFT)
    draw_text(d, (1204, 428), "IMDb 8.3/10", 18, ACCENT_DARK, "bold", "mm")
    draw_text(d, (978, 486), "Slow at first, then impossible to pause.", 28, INK, "italic", spacing=4)
    draw_text(d, (978, 618), "heart   comments   saved by friends", 16, MUTED)


def scene_discover(img, p, items):
    d = ImageDraw.Draw(img)
    nav(img)
    draw_text(d, (90, 142), "Discover", 56, INK, "bold")
    draw_text(d, (92, 210), "Fresh picks arranged by taste signals, not random lists.", 24, MUTED)

    panel = (84, 282, 1356, 720)
    add_shadow(img, panel, 36, 32, 16, 28)
    rounded(d, panel, 36, PAPER, LINE)
    draw_text(d, (122, 322), "Trending with friends", 28, INK, "bold")
    draw_text(d, (122, 362), "Movies and shows people are opening this week", 18, MUTED)

    x0 = 122
    for i in range(5):
        item = items[(i + 1) % len(items)]
        x = x0 + i * 242
        y = 420 + int(16 * (1 - ease_out(local_t(p, i * 0.08, 0.55 + i * 0.04))))
        draw_poster_card(
            img,
            item,
            x,
            y,
            178,
            236,
            label=TITLES[(i + 1) % len(TITLES)],
            meta="Movie" if i % 2 else "Series",
        )


def scene_feed(img, p, items):
    d = ImageDraw.Draw(img)
    nav(img)
    draw_text(d, (92, 140), "A feed that feels alive", 52, INK, "bold")
    draw_text(d, (94, 204), "Friends first. Discovery second. Noise last.", 24, MUTED)

    card = (230, 270, 1210, 674)
    add_shadow(img, card, 34, 36, 16, 30)
    rounded(d, card, 34, PAPER, LINE)
    avatar(d, 284, 322, "A", 58)
    draw_text(d, (364, 326), "Ayaan Rao", 24, INK, "bold")
    draw_text(d, (364, 360), "posted today", 18, MUTED)
    draw_text(d, (1086, 326), "4/5", 18, ACCENT_DARK, "bold", "mm")
    rounded(d, (1058, 303, 1114, 349), 23, SOFT)

    img.alpha_composite(poster(items[2]["poster_path"], (190, 258), 20), (284, 406))
    draw_text(d, (516, 420), "Metro After Dark", 31, INK, "bold")
    draw_text(d, (750, 425), "Movie", 21, MUTED)
    rounded(d, (822, 414, 960, 454), 20, PAPER, LINE)
    draw_text(d, (891, 434), "IMDb 8.1/10", 17, ACCENT_DARK, "bold", "mm")
    draw_text(d, (516, 478), "2026 - fictional director", 21, MUTED)
    draw_text(d, (516, 535), "A small review from someone whose taste you already trust.", 26, INK, "italic")
    draw_text(d, (516, 626), "♡ 18     ◌ 6", 25, MUTED)
    draw_text(d, (964, 626), "♥ 12    ♡ save    ↗ recommend", 25, INK)


def scene_item(img, p, items):
    d = ImageDraw.Draw(img)
    nav(img)
    card = (80, 134, 1360, 710)
    add_shadow(img, card, 36, 42, 20, 32)
    rounded(d, card, 36, PAPER, LINE)

    draw_text(d, (132, 184), "Series - 2026", 21, MUTED)
    draw_text(d, (132, 244), "Northline", 56, INK, "bold")
    draw_text(
        d,
        (134, 326),
        "A tense coastal mystery everyone in your circle starts talking about.",
        26,
        INK,
    )
    for i, (label, value) in enumerate(
        [
            ("DIRECTOR", "Mira Voss"),
            ("CAST", "Tara Vale, Kian Reed"),
            ("YEAR", "2026"),
            ("RATINGS", "IMDb 8.4/10"),
        ]
    ):
        x = 132 + i * 230
        d.line((x, 414, x + 180, 414), fill=LINE, width=1)
        draw_text(d, (x, 438), label, 16, MUTED, "bold")
        if label == "RATINGS":
            rounded(d, (x, 478, x + 146, 520), 21, PAPER, LINE)
            draw_text(d, (x + 73, 499), value, 17, ACCENT_DARK, "bold", "mm")
        else:
            draw_text(d, (x, 480), value, 22, INK, "bold")

    rounded(d, (132, 604, 310, 660), 28, ACCENT)
    draw_text(d, (221, 632), "Post your review", 19, (255, 255, 255), "bold", "mm")
    rounded(d, (326, 604, 474, 660), 28, PAPER, LINE)
    draw_text(d, (400, 632), "Save", 19, INK, "bold", "mm")
    draw_text(d, (736, 628), "♥ 32      ♡ saved      ↗ shared", 26, INK)
    img.alpha_composite(poster(items[3]["poster_path"], (270, 430), 26), (1030, 210))


def scene_close(img, p, items):
    d = ImageDraw.Draw(img)
    img.alpha_composite(WORDMARK_IMG.resize((190, int(WORDMARK_IMG.height * 190 / WORDMARK_IMG.width))), (628, 108))
    draw_text(d, (720, 292), "Reviews become recommendations\nwhen they come from people.", 58, INK, "bold", "ma", spacing=10)
    draw_text(d, (720, 466), "Discover movies, series, and books through taste you trust.", 25, MUTED, "regular", "ma")
    rounded(d, (604, 560, 838, 622), 31, ACCENT)
    draw_text(d, (721, 591), "Join Revue", 21, (255, 255, 255), "bold", "mm")


def render_frame(frame_idx: int, items: list[dict]) -> Image.Image:
    t = frame_idx / FPS
    img = BG.copy()
    if t < 3.2:
        scene_hero(img, local_t(t, 0.0, 3.2), items)
    elif t < 6.2:
        scene_discover(img, local_t(t, 3.2, 6.2), items)
    elif t < 9.2:
        scene_feed(img, local_t(t, 6.2, 9.2), items)
    elif t < 12.2:
        scene_item(img, local_t(t, 9.2, 12.2), items)
    else:
        scene_close(img, local_t(t, 12.2, 15.0), items)

    # Gentle fade at cuts and final frame.
    scene_starts = [0, 3.2, 6.2, 9.2, 12.2]
    for start in scene_starts:
        ft = t - start
        if 0 <= ft < 0.25:
            alpha = int(255 * (1 - ft / 0.25))
            overlay = Image.new("RGBA", img.size, (244, 235, 224, alpha))
            img = Image.alpha_composite(overlay, img)
    if t > 14.35:
        alpha = int(255 * clamp((t - 14.35) / 0.65))
        img = Image.alpha_composite(img, Image.new("RGBA", img.size, (244, 235, 224, alpha)))
    return img


def main():
    items = load_items()
    if len(items) < 5:
        raise RuntimeError("Need at least five cached poster images to render.")

    thumb = render_frame(int(FPS * 7.2), items)
    thumb.save(THUMB_OUT)

    frames = []
    for i in range(FRAMES):
        frame = render_frame(i, items).convert("RGB")
        frames.append(np.asarray(frame))

    import imageio.v2 as imageio

    with imageio.get_writer(MP4_OUT, fps=FPS, codec="libx264", quality=9, macro_block_size=2) as writer:
        for frame in frames:
            writer.append_data(frame)

    preview_frames = [Image.fromarray(frames[i]) for i in range(0, FRAMES, 3)]
    preview_frames[0].save(
        GIF_OUT,
        save_all=True,
        append_images=preview_frames[1:],
        duration=int(1000 / (FPS / 3)),
        loop=0,
        optimize=True,
    )
    print(MP4_OUT)
    print(GIF_OUT)
    print(THUMB_OUT)


if __name__ == "__main__":
    main()
