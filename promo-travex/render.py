#!/usr/bin/env python3
"""
Travex Global Forwarding — rendu du film promo 16:9 (1920x1080, 30 fps).

Sortie : promo-travex/export/travex-promo-16x9.mp4
Stills : python3 promo-travex/render.py --stills 3,12,20,30,45,60,70
Rendu  : python3 promo-travex/render.py
"""
import os, subprocess, argparse, glob, math, tempfile
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter
import imageio_ffmpeg

ROOT = os.path.dirname(os.path.abspath(__file__))
IMG = os.path.join(ROOT, "assets", "img")
AUD = os.path.join(ROOT, "assets", "audio")
OUT = os.path.join(ROOT, "export")
FONTDIR = os.path.join(ROOT, "..", ".claude", "skills", "short-editing", "engine", "fonts")
FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()

W, H, FPS = 1920, 1080, 30
K = 1.2
BW, BH = int(W * K), int(H * K)

INK     = (238, 242, 247)
MUTED   = (200, 208, 218)
ORANGE  = (255, 106, 26)
ORANGE2 = (255, 160, 107)
DARK    = (3, 7, 12)
BLACK   = Image.new("RGB", (W, H), (0, 0, 0))

# ------------------------------------------------------------------ typo
def font(fam, size, weight="Regular"):
    f = ImageFont.truetype(os.path.join(FONTDIR, fam), size)
    try:
        f.set_variation_by_name(weight)
    except Exception:
        pass
    return f

def tlen(text, f, tracking=0.0):
    if not text:
        return 0
    return sum(f.getlength(ch) for ch in text) + tracking * max(0, len(text) - 1)

def draw_tracked(d, xy, text, f, fill, tracking=0.0, stroke=0, stroke_fill=(0, 0, 0, 130)):
    x, y = xy
    for ch in text:
        if stroke:
            d.text((x, y), ch, font=f, fill=fill, stroke_width=stroke, stroke_fill=stroke_fill)
        else:
            d.text((x, y), ch, font=f, fill=fill)
        x += f.getlength(ch) + tracking
    return x

def ease(p):
    p = max(0.0, min(1.0, p))
    return 1 - (1 - p) ** 3

def clamp(v, a=0.0, b=1.0):
    return max(a, min(b, v))

def wrap(text, f, maxw):
    words, lines, cur = text.split(), [], ""
    for w in words:
        test = (cur + " " + w).strip()
        if not cur or tlen(test, f) <= maxw:
            cur = test
        else:
            lines.append(cur); cur = w
    if cur:
        lines.append(cur)
    return lines

# ------------------------------------------------------------------ image utils
def cover(img, w, h, focus=(0.5, 0.5)):
    iw, ih = img.size
    s = max(w / iw, h / ih)
    nw, nh = int(iw * s + 0.5), int(ih * s + 0.5)
    im = img.resize((nw, nh), Image.LANCZOS)
    x = int((nw - w) * focus[0]); y = int((nh - h) * focus[1])
    return im.crop((x, y, x + w, y + h))

def grade_layer(kind="left", w=BW, h=BH):
    g = np.zeros((h, w, 4), np.uint8)
    xs = np.linspace(0, 1, w)
    ys = np.linspace(0, 1, h)[:, None]
    if kind == "left":
        a = 0.96 * np.clip(1 - xs / 0.44, 0, 1) + 0.20 * np.clip((xs - 0.44) / 0.30, 0, 1)
        alpha = np.repeat(np.clip(a, 0.16, 0.96)[None, :], h, axis=0)
    elif kind == "center":
        r = np.sqrt((xs[None, :] - 0.5) ** 2 + ((ys - 0.45) * 0.8) ** 2)
        alpha = np.clip((r - 0.08) / 0.52, 0, 1) * 0.90 + 0.30
    else:
        alpha = np.repeat(np.full((1, w), 0.35), h, axis=0)
    vert = np.clip(1 - ys / 0.58, 0, 1) ** 1.4 * 0.74
    alpha = np.clip(np.maximum(alpha, np.repeat(vert, w, axis=1)), 0, 0.97)
    g[..., 0] = DARK[0]; g[..., 1] = DARK[1]; g[..., 2] = DARK[2]
    g[..., 3] = (alpha * 255).astype(np.uint8)
    return Image.fromarray(g, "RGBA")

_BG_CACHE = {}
def make_bg(name, grade="left", focus=(0.5, 0.5)):
    key = (name, grade, focus)
    if key in _BG_CACHE:
        return _BG_CACHE[key]
    im = Image.open(os.path.join(IMG, name)).convert("RGB")
    base = cover(im, BW, BH, focus)
    base = Image.eval(base, lambda v: int(min(255, max(0, (v - 128) * 1.07 + 126))))
    gl = grade_layer(grade, BW, BH)
    canvas = Image.new("RGBA", (BW, BH), (0, 0, 0, 255))
    canvas.paste(base, (0, 0))
    canvas.alpha_composite(gl, (0, 0))
    out = canvas.convert("RGB")
    _BG_CACHE[key] = out
    return out

_VIG = None
def vignette():
    global _VIG
    if _VIG is None:
        xs = np.linspace(-1, 1, W); ys = np.linspace(-1, 1, H)[:, None]
        r = np.sqrt(xs[None, :] ** 2 * 0.9 + ys ** 2)
        a = np.clip((r - 0.60) / 0.78, 0, 1) ** 1.3 * 0.60
        v = np.zeros((H, W, 4), np.uint8)
        v[..., 3] = (a * 255).astype(np.uint8)
        _VIG = Image.fromarray(v, "RGBA")
    return _VIG

def rounded_mask(size, radius):
    m = Image.new("L", size, 0)
    ImageDraw.Draw(m).rounded_rectangle([0, 0, size[0] - 1, size[1] - 1], radius=radius, fill=255)
    return m

# ------------------------------------------------------------------ calques
class Layer:
    __slots__ = ("img", "alpha", "xy", "t", "dur", "kind", "shift")

    def __init__(self, img, xy, t=0.0, dur=0.8, kind="rise", shift=34):
        bb = img.getbbox()
        if bb:
            img = img.crop(bb)
            xy = (xy[0] + bb[0], xy[1] + bb[1])
        self.img = img
        self.alpha = (np.asarray(img.split()[-1], dtype=np.uint8).astype(np.float32) / 255.0)
        self.xy = (float(xy[0]), float(xy[1]))
        self.t = t; self.dur = dur; self.kind = kind; self.shift = shift

    def center_x(self, canvas_w=W):
        self.xy = ((canvas_w - self.img.size[0]) / 2, self.xy[1])

# ------------------------------------------------------------------ blocs typo
def _fit(words, fam, weight, size, maxw, tracking):
    while size > 18:
        f = font(fam, size, weight)
        if max(tlen(w, f, tracking) for w in words) <= maxw:
            return f, size
        size -= 2
    return font(fam, size, weight), size

def headline(lines, fam, weight, size, maxw, tracking=-2.0, lead=1.0):
    """lines : [[(texte, couleur), ...], ...]"""
    flat = ["".join(t for t, _ in ln) for ln in lines]
    f, size = _fit(flat, fam, weight, size, maxw, tracking)
    lh = int(size * lead)
    widths = [tlen(t, f, tracking) for t in flat]
    w, h = int(max(widths)) + 10, lh * len(flat) + 10
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    y = 3
    for runs in lines:
        x = 3
        for txt, col in runs:
            x = draw_tracked(d, (x, y), txt, f, col, tracking)
        y += lh
    return im

def para(text, size=22, color=MUTED, maxw=720, lead=1.62, fam="Inter.ttf", weight="Regular"):
    f = font(fam, size, weight)
    lines = wrap(text, f, maxw)
    lh = int(size * lead)
    w = int(max(tlen(l, f) for l in lines)) + 8
    h = lh * len(lines) + 8
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    for i, l in enumerate(lines):
        d.text((3, 3 + i * lh), l, font=f, fill=color)
    return im

def kicker(num, label):
    f = font("JetBrainsMono.ttf", 15, "Medium")
    im = Image.new("RGBA", (1000, 40), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    x = draw_tracked(d, (2, 10), num, f, ORANGE, 4, 1)
    x = draw_tracked(d, (x + 12, 10), "/", f, (120, 130, 142), 4, 1)
    draw_tracked(d, (x + 12, 10), label.upper(), f, (240, 244, 249), 4, 1)
    return im.crop(im.getbbox())

def eyebrow(text):
    f = font("JetBrainsMono.ttf", 15, "Medium")
    tw = tlen(text.upper(), f, 4.2)
    w, h = int(tw + 78), 44
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle([0, 0, w - 1, h - 1], radius=h // 2, fill=(9, 15, 23, 200),
                        outline=(255, 255, 255, 52), width=1)
    d.ellipse([21, h / 2 - 4, 29, h / 2 + 4], fill=ORANGE)
    draw_tracked(d, (42, 14), text.upper(), f, (232, 238, 245), 4.2)
    return im

def chips(items, size=14):
    f = font("JetBrainsMono.ttf", size, "Medium")
    pad_x, gap, h = 16, 8, 34
    ws = [int(tlen(i.upper(), f, 3.4)) + pad_x * 2 for i in items]
    im = Image.new("RGBA", (sum(ws) + gap * (len(items) - 1) + 2, h + 2), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    x = 0
    for it, w in zip(items, ws):
        d.rounded_rectangle([x, 0, x + w, h], radius=3, fill=(14, 21, 30, 170),
                            outline=(255, 255, 255, 52), width=1)
        draw_tracked(d, (x + pad_x, 10), it.upper(), f, (216, 224, 232), 3.4)
        x += w + gap
    return im

def bullets(items, maxw=720, size=21):
    f = font("Inter.ttf", size, "Regular")
    rows = [wrap(it, f, maxw - 40) for it in items]
    lh = int(size * 1.5)
    h = sum(len(r) * lh + 12 for r in rows)
    im = Image.new("RGBA", (maxw, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    y = 0
    for lines in rows:
        cy = y + lh / 2 - 1
        d.ellipse([2, cy - 7, 16, cy + 7], outline=(255, 106, 26, 200), width=1)
        d.ellipse([6, cy - 3, 12, cy + 3], fill=ORANGE)
        for i, l in enumerate(lines):
            d.text((34, y + i * lh), l, font=f, fill=(236, 241, 247))
        y += len(lines) * lh + 12
    return im.crop(im.getbbox())

def caption(text, maxw=1180, size=21):
    f = font("Inter.ttf", size, "Regular")
    lines = wrap(text, f, maxw)
    lh = int(size * 1.5)
    tw = int(max(tlen(l, f) for l in lines))
    w, h = tw + 56, lh * len(lines) + 20
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle([0, 0, w - 1, h - 1], radius=6, fill=(6, 10, 16, 165),
                        outline=(255, 255, 255, 24), width=1)
    for i, l in enumerate(lines):
        d.text(((w - tlen(l, f)) / 2, 10 + i * lh), l, font=f, fill=(252, 253, 255))
    return im

def rule(width=300, thickness=2):
    im = Image.new("RGBA", (width, thickness), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    for x in range(width):
        a = int(255 * (1 - x / width) ** 1.2)
        if a:
            d.line([(x, 0), (x, thickness - 1)], fill=(255, 106, 26, a))
    return im

def scene_number(n, total=7):
    f = font("JetBrainsMono.ttf", 15, "Medium")
    im = Image.new("RGBA", (220, 40), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    x = draw_tracked(d, (2, 10), f"{n:02d}", f, INK, 4)
    draw_tracked(d, (x + 6, 10), f"/{total:02d}", f, (110, 120, 132), 4)
    return im.crop(im.getbbox())

def logo_lock():
    f = font("Inter.ttf", 26, "Bold")
    fm = font("JetBrainsMono.ttf", 9, "Medium")
    im = Image.new("RGBA", (420, 80), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle([0, 8, 32, 40], radius=4, fill=ORANGE)
    d.rounded_rectangle([8, 16, 24, 32], radius=2, outline=(30, 14, 4, 130), width=2)
    draw_tracked(d, (46, 10), "TRAVEX", f, INK, 5)
    draw_tracked(d, (47, 46), "GLOBAL FORWARDING", fm, (150, 160, 172), 4.6)
    return im.crop(im.getbbox())

def card(title, sub, num, w=336, h=108):
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle([0, 0, w - 1, h - 1], radius=5, fill=(10, 16, 24, 200),
                        outline=(255, 255, 255, 38), width=1)
    d.text((18, 13), num, font=font("JetBrainsMono.ttf", 11, "Medium"), fill=ORANGE)
    f = font("Inter.ttf", 21, "SemiBold")
    while tlen(title, f) > w - 36 and f.size > 12:
        f = font("Inter.ttf", f.size - 1, "SemiBold")
    d.text((18, 33), title, font=f, fill=INK)
    d.text((18, 66), sub, font=font("Inter.ttf", 15, "Regular"), fill=(158, 168, 180))
    return im

def thumb(name, w, h, label, focus=(0.5, 0.5)):
    im = cover(Image.open(os.path.join(IMG, name)).convert("RGB"), w, h, focus).convert("RGBA")
    im.putalpha(rounded_mask((w, h), 4))
    d = ImageDraw.Draw(im)
    for y in range(54):
        a = int(215 * (y / 54) ** 1.5)
        d.line([(0, h - 54 + y), (w, h - 54 + y)], fill=(4, 8, 13, a))
    f = font("JetBrainsMono.ttf", 11, "Medium")
    while tlen(label.upper(), f, 2.4) > w - 28 and f.size > 7:
        f = font("JetBrainsMono.ttf", f.size - 1, "Medium")
    draw_tracked(d, (14, h - 30), label.upper(), f, (240, 244, 248), 2.4)
    d.rounded_rectangle([0, 0, w - 1, h - 1], radius=4, outline=(255, 255, 255, 46), width=1)
    return im

def route_layer(w=720, h=520):
    pad = 34
    cw, ch = w + pad * 2, h + pad * 2
    inner = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(inner)
    for i in range(1, 7):
        d.line([(i * w / 7, 0), (i * w / 7, h)], fill=(255, 255, 255, 30), width=1)
    for i in range(1, 6):
        d.line([(0, i * h / 6), (w, i * h / 6)], fill=(255, 255, 255, 30), width=1)
    p0, p1, p2 = (80, h - 96), (300, 120), (w - 80, h - 316)
    pts = []
    for i in range(181):
        t = i / 180
        pts.append(((1 - t) ** 2 * p0[0] + 2 * (1 - t) * t * p1[0] + t * t * p2[0],
                    (1 - t) ** 2 * p0[1] + 2 * (1 - t) * t * p1[1] + t * t * p2[1]))
    d.line(pts, fill=(255, 106, 26, 235), width=3, joint="curve")
    d.ellipse([p0[0] - 8, p0[1] - 8, p0[0] + 8, p0[1] + 8], fill=(255, 255, 255, 255))
    d.ellipse([p0[0] - 18, p0[1] - 18, p0[0] + 18, p0[1] + 18], outline=(255, 255, 255, 105), width=2)
    d.ellipse([p2[0] - 8, p2[1] - 8, p2[0] + 8, p2[1] + 8], fill=ORANGE)
    d.ellipse([p2[0] - 24, p2[1] - 24, p2[0] + 24, p2[1] + 24], outline=(255, 106, 26, 140), width=2)
    fm = font("JetBrainsMono.ttf", 13, "Medium")
    t1 = "RENCHEN · DE"
    draw_tracked(d, (p0[0] - tlen(t1, fm, 3.6) / 2, p0[1] + 30), t1, fm, (255, 255, 255), 3.6)
    t2 = "DOUALA · CM"
    draw_tracked(d, (p2[0] - tlen(t2, fm, 3.6) / 2, p2[1] - 50), t2, fm, ORANGE2, 3.6)

    im = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
    dd = ImageDraw.Draw(im)
    dd.rounded_rectangle([0, 0, cw - 1, ch - 1], radius=10, fill=(6, 11, 18, 172),
                         outline=(255, 255, 255, 46), width=1)
    im.alpha_composite(inner, (pad, pad))
    return im

def pill(text, size=22):
    f = font("Inter.ttf", size, "Bold")
    tw = tlen(text, f)
    w, h = int(tw + 128), 64
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle([0, 0, w - 1, h - 1], radius=h // 2, fill=(255, 96, 18))
    d.text(((w - tw) / 2 - 16, 19), text, font=f, fill=(26, 10, 0))
    d.text((w - 62, 14), "→", font=font("Inter.ttf", 26, "Bold"), fill=(26, 10, 0))
    return im

def place_card(city, cc, lines, w=430, h=152):
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle([0, 0, w - 1, h - 1], radius=6, fill=(9, 15, 23, 232),
                        outline=(255, 255, 255, 60), width=1)
    fc = font("Inter.ttf", 20, "SemiBold")
    d.text((20, 18), city, font=fc, fill=INK)
    draw_tracked(d, (28 + tlen(city, fc), 25), cc, font("JetBrainsMono.ttf", 10, "Medium"), ORANGE, 3)
    fl = font("Inter.ttf", 14, "Regular")
    for i, l in enumerate(lines):
        d.text((20, 54 + i * 24), l, font=fl, fill=(196, 205, 216))
    return im

def footer_line():
    fm = font("JetBrainsMono.ttf", 14, "Medium")
    t = "MORE PERFORMANCE — MORE SUCCESS"
    tw = tlen(t, fm, 5)
    w, h = int(tw + 84), 46
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle([0, 0, w - 1, h - 1], radius=23, fill=(6, 10, 16, 170),
                        outline=(255, 255, 255, 40), width=1)
    draw_tracked(d, (32, 15), t, fm, (238, 243, 250), 5, 1)
    return im

# ------------------------------------------------------------------ fonds vidéo
VIDEO_DIR = os.path.join(ROOT, "assets", "video")
STEMS = {1: "06-douala", 2: "01-air-freight", 3: "02-sea-containers", 4: "04-roro-vehicles",
         5: "03-warehouse", 6: "07-trust-team", 7: "05-truck-europe"}
EXTS = (".mp4", ".mov", ".m4v", ".webm", ".mkv")
ZOOM_IN = 1.12   # recadrage : sort les filigranes d'angle du cadre
SLOWMO = 1.00    # 1.6 = un clip de 5 s tient 8 s (aucun son conservé)

class VideoSource:
    """Un rush fourni par le client : boucle en ping-pong, cadré en 1920x1080."""

    def __init__(self, path, w=W, h=H):
        self.path = path
        self.dir = tempfile.mkdtemp(prefix="travex_bg_")
        out = os.path.join(self.dir, "f%05d.jpg")
        zw, zh = int(w * ZOOM_IN), int(h * ZOOM_IN)
        vf = (f"scale={zw}:{zh}:force_original_aspect_ratio=increase,crop={zw}:{zh},"
              f"setpts=(PTS-STARTPTS)/{SLOWMO},fps={FPS},"
              f"scale={w}:{h},eq=contrast=1.04:saturation=0.95")
        subprocess.run([FFMPEG, "-y", "-hide_banner", "-loglevel", "error",
                        "-i", path, "-vf", vf, "-q:v", "3", out], check=True)
        self.frames = sorted(glob.glob(os.path.join(self.dir, "*.jpg")))
        if not self.frames:
            raise RuntimeError(f"aucune image extraite de {path}")
        self.n = len(self.frames)
        self._cache_i = -1
        self._cache_img = None

    def frame(self, local):
        i = int(local * FPS)
        if i >= self.n:                                  # ping-pong : pas de saut
            span = max(1, (self.n - 1) * 2)
            i = i % span
            if i >= self.n:
                i = span - i
        if i != self._cache_i:
            self._cache_img = Image.open(self.frames[i]).convert("RGB")
            self._cache_i = i
        return self._cache_img

    def close(self):
        try:
            subprocess.run(["rm", "-rf", self.dir])
        except Exception:
            pass

def load_videos():
    found = {}
    if not os.path.isdir(VIDEO_DIR):
        return found
    for idx, stem in STEMS.items():
        for ext in EXTS:
            p = os.path.join(VIDEO_DIR, stem + ext)
            if os.path.exists(p):
                try:
                    found[idx] = VideoSource(p)
                    print(f"fond vidéo : scène {idx} <- {os.path.basename(p)}")
                except Exception as e:
                    print(f"!! {p} illisible ({e})")
                break
    return found

VIDEOS = {}

# ------------------------------------------------------------------ atmosphère
_STYLE = {
    1: dict(grade="left",   fog=0.070, warm=True,  sweep=0.050, dust=0),
    2: dict(grade="left",   fog=0.060, warm=False, sweep=0.040, dust=0),
    3: dict(grade="left",   fog=0.065, warm=True,  sweep=0.045, dust=0),
    4: dict(grade="left",   fog=0.070, warm=False, sweep=0.030, dust=0),
    5: dict(grade="left",   fog=0.040, warm=True, sweep=0.035, dust=1),
    6: dict(grade="left",   fog=0.035, warm=True,  sweep=0.025, dust=1),
    7: dict(grade="center", fog=0.055, warm=True,  sweep=0.045, dust=0),
}

def _cloud(w, h, cells, seed, blur):
    rng = np.random.default_rng(seed)
    small = rng.random((cells, max(2, int(cells * h / w)))).astype(np.float32)
    im = Image.fromarray((small * 255).astype(np.uint8), "L").resize((w, h), Image.BICUBIC)
    return np.asarray(im.filter(ImageFilter.GaussianBlur(blur)), np.float32) / 255.0

_FOG = {}
def fog_layer(warm=True, size=(W + 240, H + 240)):
    key = (warm, size)
    if key in _FOG:
        return _FOG[key]
    w, h = size
    a = 0.62 * _cloud(w, h, 7, 11, 26) + 0.38 * _cloud(w, h, 19, 7, 9)
    a = np.clip((a - 0.34) * 2.1, 0, 1) ** 1.25
    tint = (255, 236, 220) if warm else (206, 220, 238)
    arr = np.zeros((h, w, 4), np.uint8)
    arr[..., 0], arr[..., 1], arr[..., 2] = tint
    arr[..., 3] = (a * 255).astype(np.uint8)
    _FOG[key] = Image.fromarray(arr, "RGBA")
    return _FOG[key]

_SWEEP = {}
def sweep_layer(size=(W + 600, H)):
    if size in _SWEEP:
        return _SWEEP[size]
    w, h = size
    xs = np.linspace(0, 1, w)[None, :]
    band = np.exp(-((xs - 0.5) ** 2) / 0.0022) * 0.9 + np.exp(-((xs - 0.18) ** 2) / 0.010) * 0.35
    arr = np.zeros((h, w, 4), np.uint8)
    arr[..., 0], arr[..., 1], arr[..., 2] = (255, 246, 236)
    arr[..., 3] = (np.clip(band, 0, 1) * 255).astype(np.uint8)
    _SWEEP[size] = Image.fromarray(arr, "RGBA")
    return _SWEEP[size]

_GRAIN = []
def grain_frames(n=5):
    if _GRAIN:
        return _GRAIN
    rng = np.random.default_rng(42)
    for _ in range(n):
        a = rng.normal(128, 26, (H, W, 1)).repeat(3, axis=2)
        _GRAIN.append(Image.fromarray(np.clip(a, 0, 255).astype(np.uint8), "RGB"))
    return _GRAIN

def dust_sprite():
    s = 26
    im = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    for r in range(s // 2, 0, -1):
        alpha = int(62 * (1 - r / (s / 2)) ** 1.6)
        d.ellipse([s / 2 - r, s / 2 - r, s / 2 + r, s / 2 + r], fill=(255, 240, 222, alpha))
    return im

DUST = [(np.random.default_rng(i).random(), np.random.default_rng(i + 100).random(),
         np.random.default_rng(i + 200).random()) for i in range(70)]

def atmosphere(im, style, local, frame_no):
    """Brume qui dérive, balayage de lumière, poussière, grain : le plan bouge vraiment."""
    # brume
    fstr = style["fog"]
    if fstr > 0:
        fog = fog_layer(style["warm"])
        ox = int(120 + 90 * math.sin(local * 0.11))
        oy = int(120 + 60 * math.cos(local * 0.08))
        part = fog.crop((ox, oy, ox + W, oy + H))
        a = np.asarray(part.split()[-1], np.float32) / 255.0 * fstr
        part.putalpha(Image.fromarray((a * 255).astype(np.uint8)))
        im.alpha_composite(part)
    # balayage de lumière
    sstr = style["sweep"]
    if sstr > 0:
        sw = sweep_layer()
        ox = int(300 + 220 * math.sin(local * 0.16 + 1.2))
        part = sw.crop((ox, 0, ox + W, H))
        a = np.asarray(part.split()[-1], np.float32) / 255.0 * sstr
        part.putalpha(Image.fromarray((a * 255).astype(np.uint8)))
        im.alpha_composite(part)
    # poussière en suspension (intérieurs)
    if style["dust"]:
        sprite = dust_sprite()
        for i, (x0, y0, sp) in enumerate(DUST[:46]):
            y = (y0 * H - local * (14 + 18 * sp)) % H
            x = (x0 * W + 26 * math.sin(local * (0.35 + 0.3 * sp) + i)) % W
            im.alpha_composite(sprite, (int(x), int(y)))
    # grain image par image
    g = grain_frames()[frame_no % len(grain_frames())]
    im = Image.blend(im, g.convert("RGBA"), 0.045)
    return im

def grade_full(kind):
    key = ("full", kind)
    if key not in _BG_CACHE:
        _BG_CACHE[key] = grade_layer(kind, W, H)
    return _BG_CACHE[key]

# ------------------------------------------------------------------ construction
def build_scenes():
    S = []

    # ---------- 1 · ouverture
    s = dict(start=0.0, dur=14.0, bg=make_bg("06-douala.jpg", "left", (0.55, 0.5)),
             zoom=(1.0, 1.12), focus=(0.60, 0.46), layers=[])
    L = s["layers"]
    L.append(Layer(eyebrow("Renchen, Allemagne · Douala, Cameroun"), (123, 116), 0.15, 0.7, "fade"))
    L.append(Layer(headline([[("Vos marchandises", INK)],
                             [("méritent mieux", INK)],
                             [("qu'un simple transport.", ORANGE)]],
                            "Inter.ttf", "Bold", 86, 1060, -2.6, 1.02), (123, 200), 0.45, 0.95, "rise", 44))
    L.append(Layer(rule(300, 2), (123, 500), 1.25, 1.0, "grow"))
    L.append(Layer(para("Fret aérien, maritime, Ro-Ro, entreposage, import-export et douane : "
                        "un seul interlocuteur, du premier kilomètre à la livraison finale.",
                        22, MUTED, 690), (123, 542), 1.45, 0.9, "fade"))
    L.append(Layer(chips(["IATA", "OEA", "ISO 9001"]), (123, 672), 1.85, 0.7, "fade"))
    L.append(Layer(route_layer(), (1040, 268), 1.1, 0.9, "fade"))
    L.append(Layer(scene_number(1), (1692, 104), 0.2, 0.6, "fade"))
    c = Layer(caption("De l'Allemagne au Cameroun, et partout dans le monde : Travex organise vos "
                      "expéditions, du premier kilomètre à la livraison finale."), (0, 936), 0.9, 0.6, "fade")
    c.center_x(); L.append(c)
    S.append(s)

    # ---------- 2 · fret aérien
    s = dict(start=14.0, dur=10.4, bg=make_bg("01-air-freight.jpg", "left", (0.5, 0.5)),
             zoom=(1.0, 1.10), focus=(0.44, 0.5), layers=[])
    L = s["layers"]
    L.append(Layer(kicker("01", "Fret aérien"), (123, 148), 0.1, 0.6, "fade"))
    L.append(Layer(headline([[("Quand chaque", INK)], [("heure compte.", ORANGE)]],
                            "Inter.ttf", "Bold", 82, 760, -2.4, 1.04), (123, 196), 0.28, 0.85, "rise", 42))
    L.append(Layer(para("Nos partenaires aériens spécialisés font partir vos envois urgents et vos "
                        "marchandises de valeur, avec un délai de transport réduit.",
                        22, MUTED, 680), (123, 400), 0.55, 0.8, "fade"))
    L.append(Layer(bullets(["Marchandises urgentes et envois de valeur",
                            "Réseau de partenaires et de compagnies aériennes",
                            "Prise en charge et suivi de bout en bout"], 720), (123, 534), 0.85, 0.85, "left", 40))
    L.append(Layer(chips(["Aérien", "Porte-à-porte", "Urgent"]), (123, 752), 1.4, 0.7, "fade"))
    L.append(Layer(scene_number(2), (1692, 104), 0.2, 0.6, "fade"))
    c = Layer(caption("Fret aérien : quand chaque heure compte, vos envois urgents et vos marchandises "
                      "de valeur arrivent vite, en toute sécurité."), (0, 936), 0.7, 0.6, "fade")
    c.center_x(); L.append(c)
    S.append(s)

    # ---------- 3 · maritime
    s = dict(start=24.4, dur=9.6, bg=make_bg("02-sea-containers.jpg", "left", (0.68, 0.5)),
             zoom=(1.0, 1.10), focus=(0.46, 0.52), layers=[])
    L = s["layers"]
    L.append(Layer(kicker("02", "Fret maritime"), (123, 148), 0.1, 0.6, "fade"))
    L.append(Layer(headline([[("Conteneurs &", INK)], [("groupage.", ORANGE)]],
                            "Inter.ttf", "Bold", 82, 760, -2.4, 1.04), (123, 196), 0.28, 0.85, "rise", 42))
    L.append(Layer(para("Un réseau de partenaires spécialisés et de compagnies maritimes, pour des "
                        "solutions adaptées à vos volumes comme à vos destinations.",
                        22, MUTED, 680), (123, 400), 0.55, 0.8, "fade"))
    L.append(Layer(bullets(["Conteneur complet ou groupage (LCL)",
                            "Mise à disposition, préparation et expédition",
                            "Départs réguliers vers l'Afrique de l'Ouest et centrale"], 720),
                   (123, 534), 0.85, 0.85, "left", 40))
    L.append(Layer(chips(["FCL", "LCL", "Conteneurs"]), (123, 752), 1.4, 0.7, "fade"))
    L.append(Layer(scene_number(3), (1692, 104), 0.2, 0.6, "fade"))
    c = Layer(caption("Fret maritime, conteneurs et groupage : des solutions flexibles, adaptées à vos "
                      "volumes comme à vos destinations."), (0, 936), 0.7, 0.6, "fade")
    c.center_x(); L.append(c)
    S.append(s)

    # ---------- 4 · Ro-Ro
    s = dict(start=34.0, dur=7.9, bg=make_bg("04-roro-vehicles.jpg", "left", (0.5, 0.5)),
             zoom=(1.0, 1.14), focus=(0.56, 0.5), layers=[])
    L = s["layers"]
    L.append(Layer(kicker("03", "Ro-Ro & véhicules"), (123, 148), 0.1, 0.6, "fade"))
    L.append(Layer(headline([[("Vos véhicules,", INK)], [("embarqués à bord.", ORANGE)]],
                            "Inter.ttf", "Bold", 78, 800, -2.3, 1.04), (123, 196), 0.28, 0.85, "rise", 42))
    L.append(Layer(para("Voitures et engins expédiés par navires spécialement conçus pour leur transport, "
                        "en collaboration avec nos partenaires et les compagnies maritimes.",
                        22, MUTED, 680), (123, 398), 0.58, 0.8, "fade"))
    L.append(Layer(bullets(["Roll-on / Roll-off, en direct à bord",
                            "Véhicules, engins et matériel roulant"], 720), (123, 540), 0.9, 0.85, "left", 40))
    L.append(Layer(scene_number(4), (1692, 104), 0.2, 0.6, "fade"))
    c = Layer(caption("Véhicules et engins : embarquement Ro-Ro vers l'international, avec des "
                      "compagnies maritimes spécialisées."), (0, 936), 0.7, 0.6, "fade")
    c.center_x(); L.append(c)
    S.append(s)

    # ---------- 5 · logistique
    s = dict(start=41.9, dur=13.8, bg=make_bg("03-warehouse.jpg", "left", (0.55, 0.55)),
             zoom=(1.02, 1.12), focus=(0.48, 0.5), layers=[])
    L = s["layers"]
    L.append(Layer(kicker("04", "Logistique & entrepôt — Renchen"), (110, 104), 0.1, 0.6, "fade"))
    L.append(Layer(headline([[("Réceptionner,", INK)], [("stocker, préparer.", ORANGE)]],
                            "Inter.ttf", "Bold", 66, 650, -2.0, 1.05), (110, 146), 0.28, 0.85, "rise", 38))
    L.append(Layer(para("Notre plateforme logistique de Renchen accompagne vos opérations d'import et "
                        "d'export : emballage, entreposage sécurisé, préparation puis départ.",
                        20, MUTED, 620), (110, 302), 0.55, 0.8, "fade"))
    L.append(Layer(card("Emballage & stockage", "Conditionnement et protection", "01"), (110, 420), 0.85, 0.65, "fade"))
    L.append(Layer(card("Entreposage sécurisé", "Allemagne & international", "02"), (462, 420), 0.97, 0.65, "fade"))
    L.append(Layer(card("Transport terrestre", "Groupage et lots complets", "03"), (110, 542), 1.09, 0.65, "fade"))
    L.append(Layer(card("Import / export & douane", "Formalités et pilotage des flux", "04"), (462, 542), 1.21, 0.65, "fade"))
    L.append(Layer(thumb("03-warehouse.jpg", 360, 250, "Plateforme · Renchen", (0.35, 0.5)), (948, 168), 1.40, 0.8, "right", 46))
    L.append(Layer(thumb("05-truck-europe.jpg", 360, 250, "Transport terrestre"), (1336, 168), 1.52, 0.8, "right", 46))
    L.append(Layer(thumb("02-sea-containers.jpg", 748, 230, "Départs conteneurs · Europe → Afrique", (0.7, 0.5)),
                   (948, 438), 1.66, 0.8, "right", 46))
    L.append(Layer(scene_number(5), (1692, 104), 0.2, 0.6, "fade"))
    c = Layer(caption("À Renchen, notre plateforme réceptionne, stocke et prépare vos marchandises. "
                      "Import, export, douane : nous pilotons chaque étape."), (0, 936), 0.7, 0.6, "fade")
    c.center_x(); L.append(c)
    S.append(s)

    # ---------- 6 · humain
    s = dict(start=55.7, dur=9.0, bg=make_bg("07-trust-team.jpg", "left", (0.38, 0.45)),
             zoom=(1.02, 1.14), focus=(0.42, 0.45), layers=[])
    L = s["layers"]
    L.append(Layer(kicker("05", "Notre différence"), (123, 148), 0.1, 0.6, "fade"))
    q = Image.new("RGBA", (120, 120), (0, 0, 0, 0))
    ImageDraw.Draw(q).text((0, -14), "\u201c", font=font("Inter.ttf", 150, "Bold"), fill=(255, 106, 26, 100))
    L.append(Layer(q, (121, 176), 0.3, 0.6, "fade"))
    L.append(Layer(headline([[("Un interlocuteur.", INK)],
                             [("Pas un guichet.", INK)],
                             [("Nous nous adaptons", INK)],
                             [("à vos besoins, pas l'inverse.", ORANGE)]],
                            "Inter.ttf", "SemiBold", 56, 830, -1.4, 1.18), (123, 300), 0.42, 0.9, "rise", 38))
    L.append(Layer(para("Notre personnel donne une touche personnelle à chaque dossier et vous accompagne "
                        "tout au long du processus, jusqu'à bâtir une relation de confiance durable.",
                        21, MUTED, 690), (123, 640), 1.1, 0.8, "fade"))
    L.append(Layer(chips(["Sur mesure", "Un interlocuteur", "Relation durable"]), (123, 762), 1.3, 0.7, "fade"))
    L.append(Layer(scene_number(6), (1692, 104), 0.2, 0.6, "fade"))
    c = Layer(caption("Et surtout, un interlocuteur. Pas un guichet. Nous apprenons à vous connaître, "
                      "et nous nous adaptons à vos besoins."), (0, 936), 0.7, 0.6, "fade")
    c.center_x(); L.append(c)
    S.append(s)

    # ---------- 7 · CTA
    s = dict(start=64.7, dur=12.4, bg=make_bg("05-truck-europe.jpg", "center", (0.5, 0.55)),
             zoom=(1.0, 1.12), focus=(0.5, 0.5), layers=[])
    L = s["layers"]
    lg = Layer(logo_lock(), (0, 148), 0.2, 0.7, "fade"); lg.center_x(); L.append(lg)
    cta = Layer(headline([[("Demandez votre ", INK), ("cotation gratuite", ORANGE), (".", INK)]],
                         "Inter.ttf", "Bold", 68, 1240, -2.2, 1.05), (0, 262), 0.45, 0.9, "rise", 38)
    cta.center_x(); L.append(cta)
    p = Layer(pill("travex-global-forwarding.com"), (0, 392), 1.05, 0.7, "scale"); p.center_x(); L.append(p)
    c1 = Layer(place_card("Renchen", "ALLEMAGNE · SIÈGE",
                          ["Im Brünnel 2 — 77871 Renchen", "+49 176 506 18495",
                           "info@travexglobalforwarding.com"]), (W / 2 - 450, 508), 1.35, 0.75, "left", 46)
    c2 = Layer(place_card("Douala", "CAMEROUN",
                          ["Bonamoussadi", "Liaison Francfort → Douala",
                           "Contact : +49 176 506 18495"]), (W / 2 + 20, 508), 1.5, 0.75, "right", 46)
    L += [c1, c2]
    ft = Layer(footer_line(), (0, 700), 1.9, 0.8, "fade"); ft.center_x(); L.append(ft)
    ch = Layer(chips(["IATA", "OEA", "ISO 9001", "Allemagne · France · Suisse"], 13), (0, 758), 2.1, 0.8, "fade")
    ch.center_x(); L.append(ch)
    c = Layer(caption("Travex Global Forwarding. Renchen, Allemagne. Douala, Cameroun. "
                      "Plus de performance, plus de succès."), (0, 936), 0.9, 0.6, "fade")
    c.center_x(); L.append(c)
    S.append(s)

    return S

SCENES = build_scenes()
TOTAL = SCENES[-1]["start"] + SCENES[-1]["dur"]

VO = [("vo-01.mp3", 0.55), ("vo-02.mp3", 0.35), ("vo-03.mp3", 0.35), ("vo-04.mp3", 0.35),
      ("vo-05.mp3", 0.35), ("vo-06.mp3", 0.35), ("vo-07.mp3", 0.45)]

# ------------------------------------------------------------------ image
def scene_at(t):
    idx = 0
    for j, s in enumerate(SCENES):
        if t >= s["start"]:
            idx = j
    return idx

def frame(scene_idx, local):
    sc = SCENES[scene_idx]
    style = _STYLE[scene_idx + 1]
    p = clamp(local / sc["dur"])

    if (scene_idx + 1) in VIDEOS:                      # ---- fond = rush vidéo
        im = VIDEOS[scene_idx + 1].frame(local).convert("RGBA")
        im.alpha_composite(grade_full(style["grade"]))
    else:                                              # ---- fond = photo animée
        z0, z1 = sc["zoom"]
        # respiration lente de la caméra, comme un vrai opérateur
        z = z0 + (z1 - z0) * p + 0.006 * math.sin(local * 0.9)
        win_w, win_h = BW / z, BH / z
        fx = clamp(sc["focus"][0] + 0.030 * (p - 0.5) + 0.008 * math.sin(local * 0.55))
        fy = clamp(sc["focus"][1] + 0.012 * math.cos(local * 0.42), 0.05, 0.95)
        cx = clamp(fx * BW, win_w / 2, BW - win_w / 2)
        cy = clamp(fy * BH, win_h / 2, BH - win_h / 2)
        box = (int(cx - win_w / 2), int(cy - win_h / 2), int(cx + win_w / 2), int(cy + win_h / 2))
        im = sc["bg"].crop(box).resize((W, H), Image.BILINEAR).convert("RGBA")

    im = atmosphere(im, style, local, int(local * FPS))

    for l in sc["layers"]:
        pr = (local - l.t) / l.dur
        if pr <= 0:
            continue
        e = ease(pr)
        dx = dy = 0
        if l.kind == "rise":
            dy = int(l.shift * (1 - e))
        elif l.kind == "left":
            dx = int(-l.shift * (1 - e))
        elif l.kind == "right":
            dx = int(l.shift * (1 - e))
        if l.kind == "grow":
            wpx = max(1, int(l.img.size[0] * e))
            crop = l.img.crop((0, 0, wpx, l.img.size[1])).copy()
            a = np.asarray(crop.split()[-1], np.float32) * e
            crop.putalpha(Image.fromarray(a.astype(np.uint8)))
            im.paste(crop, (int(l.xy[0]), int(l.xy[1])), crop)
            continue
        if l.kind == "scale":
            sc_ = 0.92 + 0.08 * e
            nw, nh = max(1, int(l.img.size[0] * sc_)), max(1, int(l.img.size[1] * sc_))
            c = l.img.resize((nw, nh), Image.BILINEAR)
            base = np.asarray(c.split()[-1], np.float32)
            c.putalpha(Image.fromarray((base * e).astype(np.uint8)))
            im.paste(c, (int(l.xy[0] + (l.img.size[0] - nw) / 2),
                         int(l.xy[1] + (l.img.size[1] - nh) / 2)), c)
            continue
        if e <= 0.002:
            continue
        tmp = l.img.copy()
        tmp.putalpha(Image.fromarray((l.alpha * e * 255).astype(np.uint8)))
        im.paste(tmp, (int(l.xy[0]) + dx, int(l.xy[1]) + dy), tmp)

    im.alpha_composite(vignette())

    # fondu d'ouverture / de fermeture
    if local < 0.8 and scene_idx == 0:
        im = Image.blend(im, BLACK.convert("RGBA"), 1 - ease(local / 0.8))
    last = scene_idx == len(SCENES) - 1
    if last and local > SCENES[scene_idx]["dur"] - 1.0:
        k = ease((local - (SCENES[scene_idx]["dur"] - 1.0)) / 1.0)
        im = Image.blend(im, BLACK.convert("RGBA"), k)
    return im

def sc_dur_last(i):
    return SCENES[i]["dur"]

# ------------------------------------------------------------------ audio
def audio_filter():
    parts, labels = [], []
    for i, (f, off) in enumerate(VO):
        ms = int(round((SCENES[i]["start"] + off) * 1000))
        parts.append(f"[{i + 1}:a]adelay={ms}|{ms}[a{i}]")
        labels.append(f"[a{i}]")
    mix = ("".join(labels) +
           f"amix=inputs={len(VO)}:normalize=0:dropout_transition=0,"
           f"loudnorm=I=-16:TP=-1.5:LRA=11,apad,atrim=0:{TOTAL}[aout]")
    return ";".join(parts) + ";" + mix

# ------------------------------------------------------------------ sortie
def render(out_path):
    global VIDEOS
    VIDEOS = load_videos()
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    total = int(round(TOTAL * FPS))
    cmd = [FFMPEG, "-y", "-hide_banner", "-loglevel", "error",
           "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-"]
    for f, _ in VO:
        cmd += ["-i", os.path.join(AUD, f)]
    cmd += ["-filter_complex", audio_filter(),
            "-map", "0:v", "-map", "[aout]",
            "-c:v", "libx264", "-preset", "medium", "-crf", "20",
            "-pix_fmt", "yuv420p", "-profile:v", "high", "-level", "4.1",
            "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
            "-movflags", "+faststart", "-t", f"{TOTAL}", out_path]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    for i in range(total):
        t = i / FPS
        idx = scene_at(t)
        fr = frame(idx, t - SCENES[idx]["start"])
        proc.stdin.write(fr.convert("RGB").tobytes())
        if i % 90 == 0:
            print(f"  {i}/{total}  {t:5.1f}s", flush=True)
    proc.stdin.close()
    if proc.wait() != 0:
        raise SystemExit("ffmpeg a échoué")
    print("OK ->", out_path)

def still(t, path):
    idx = scene_at(t)
    fr = frame(idx, t - SCENES[idx]["start"])
    fr.convert("RGB").save(path, quality=92)
    print("still ->", path)

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--stills", default="")
    ap.add_argument("--out", default=os.path.join(OUT, "travex-promo-16x9.mp4"))
    a = ap.parse_args()
    if a.stills:
        d = os.path.join(OUT, "stills"); os.makedirs(d, exist_ok=True)
        for ts in a.stills.split(","):
            still(float(ts), os.path.join(d, f"t{float(ts):05.1f}.jpg"))
    else:
        render(a.out)
