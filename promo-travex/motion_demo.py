#!/usr/bin/env python3
"""
Démo « motion design » : 10 s entièrement générées, aucune photo.
Sol en perspective qui avance, halo qui respire, trajet qui se trace,
avion qui suit la courbe, cartouches de modes, logo.

    python3 promo-travex/motion_demo.py
    -> promo-travex/export/demo-motion-10s.mp4
"""
import os, re, math, subprocess
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter
import imageio_ffmpeg

ROOT = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(ROOT, "export", "demo-motion-10s.mp4")
FONTDIR = os.path.join(ROOT, "..", ".claude", "skills", "short-editing", "engine", "fonts")
FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()

W, H, FPS, DUR = 1920, 1080, 30, 10.0
INK, MUTED, ORANGE, ORANGE2 = (238, 242, 247), (188, 198, 210), (255, 106, 26), (255, 160, 107)
VP = (960, 604)          # point de fuite


def font(fam, size, weight="Regular"):
    f = ImageFont.truetype(os.path.join(FONTDIR, fam), size)
    try:
        f.set_variation_by_name(weight)
    except Exception:
        pass
    return f


def tracked(d, xy, text, f, fill, tr=0.0):
    x, y = xy
    for ch in text:
        d.text((x, y), ch, font=f, fill=fill)
        x += f.getlength(ch) + tr
    return x


def ease(p):
    p = max(0.0, min(1.0, p))
    return 1 - (1 - p) ** 3


def clamp(v, a=0.0, b=1.0):
    return max(a, min(b, v))


# ---------------------------------------------------------------- fond
def background():
    """Ciel dégradé + halo : calculé une fois."""
    ys = np.linspace(0, 1, H)[:, None]
    top = np.array([7, 12, 22], float)
    bottom = np.array([3, 6, 11], float)
    grad = top * (1 - ys) + bottom * ys
    arr = np.repeat(grad[:, None, :], W, axis=1)

    xs = np.linspace(0, 1, W)[None, :]
    glow = np.exp(-(((xs - 0.52) ** 2) / 0.055 + ((ys - 0.46) ** 2) / 0.085))
    arr += glow[..., None] * np.array([120, 62, 26], float)

    band = np.exp(-(((ys - 0.30) ** 2) / 0.02)) * 0.06
    arr += band[..., None] * np.array([255, 210, 180], float)
    return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), "RGB")


BG = background()


def floor_grid(t):
    """Sol en perspective qui défile vers la caméra."""
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    scroll = (t * 0.55) % 1.0
    for i in range(14):
        k = ((i + scroll) / 14) ** 2.4
        y = VP[1] + k * (H - VP[1]) * 1.35
        if y > H + 40:
            continue
        a = int(clamp(1 - k * 0.85) * 105)
        d.line([(0, y), (W, y)], fill=(120, 150, 190, a), width=1)
    for i in range(-13, 14):
        if i == 0:
            continue
        x_bottom = W / 2 + i * (W / 12)
        a = int(34 * clamp(1 - abs(i) / 14))
        d.line([VP, (x_bottom, H)], fill=(110, 145, 185, a), width=1)
    return layer.filter(ImageFilter.GaussianBlur(0.6))


def glow_at(t):
    """Halo qui respire, en haut du sol."""
    r = 300 + 60 * math.sin(t * 0.9)
    g = Image.new("RGBA", (int(r * 2.4), int(r * 1.2)), (0, 0, 0, 0))
    d = ImageDraw.Draw(g)
    for i in range(26):
        k = 1 - i / 26
        d.ellipse([g.size[0] / 2 - r * k, g.size[1] / 2 - r * 0.42 * k,
                   g.size[0] / 2 + r * k, g.size[1] / 2 + r * 0.42 * k],
                  fill=(255, 130, 60, int(3.2 * (1 - k) * 10)))
    g = g.filter(ImageFilter.GaussianBlur(40))
    return g


# ---------------------------------------------------------------- trajet
P0, P1, P2 = (250, 742), (760, 300), (1660, 470)


def bez(t):
    return ((1 - t) ** 2 * P0[0] + 2 * (1 - t) * t * P1[0] + t * t * P2[0],
            (1 - t) ** 2 * P0[1] + 2 * (1 - t) * t * P1[1] + t * t * P2[1])


def plane_sprite(size=44, color=ORANGE):
    im = Image.new("RGBA", (size * 2, size * 2), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    s = size
    d.polygon([(s * 1.15, s), (s * 0.15, s * 0.55), (s * 0.45, s), (s * 0.15, s * 1.45)],
              fill=color)
    d.polygon([(s * 1.15, s), (s * 0.62, s), (s * 0.78, s * 0.72)], fill=(255, 200, 170))
    return im


PLANE = plane_sprite()


def route_layer(progress):
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    n = 220
    pts = [bez(i / n) for i in range(n + 1)]
    cut = int(n * progress)
    if cut > 1:
        d.line(pts[:cut], fill=(255, 106, 26, 235), width=4, joint="curve")
        # halo du tracé
        for w, a in ((14, 22), (8, 34)):
            d.line(pts[max(0, cut - 40):cut], fill=(255, 120, 40, a), width=w, joint="curve")
    # départ / arrivée
    if progress > 0.02:
        d.ellipse([P0[0] - 8, P0[1] - 8, P0[0] + 8, P0[1] + 8], fill=(255, 255, 255, 255))
        d.ellipse([P0[0] - 20, P0[1] - 20, P0[0] + 20, P0[1] + 20],
                  outline=(255, 255, 255, 90), width=2)
    if progress > 0.98:
        d.ellipse([P2[0] - 9, P2[1] - 9, P2[0] + 9, P2[1] + 9], fill=(255, 106, 26, 255))
        d.ellipse([P2[0] - 26, P2[1] - 26, P2[0] + 26, P2[1] + 26],
                  outline=(255, 106, 26, 140), width=2)
    return layer


def plane_at(progress):
    p = clamp(progress)
    x, y = bez(p)
    x2, y2 = bez(min(1.0, p + 0.01))
    ang = math.degrees(math.atan2(y2 - y, x2 - x))
    img = PLANE.rotate(-ang, resample=Image.BICUBIC, expand=False)
    return img, (int(x - PLANE.size[0] / 2), int(y - PLANE.size[1] / 2))


# ---------------------------------------------------------------- typo
def text_layer(lines, size, weight, maxw=None, lead=1.05, color=INK, tr=-2.0, fam="Inter.ttf"):
    """**texte** = segment orange."""
    if isinstance(lines, str):
        lines = [lines]
    f = font(fam, size, weight)
    lh = int(size * lead)
    parsed = []
    for ln in lines:
        segs = []
        for part in re.split(r"(\*\*[^*]+\*\*)", ln):
            if not part:
                continue
            if part.startswith("**") and part.endswith("**"):
                segs.append((part[2:-2], ORANGE))
            else:
                segs.append((part, color))
        parsed.append(segs)
    widths = []
    for segs in parsed:
        n = sum(len(t) for t, _ in segs)
        widths.append(sum(f.getlength(t) for t, _ in segs) + tr * max(0, n - 1))
    im = Image.new("RGBA", (int(max(widths)) + 8, lh * len(parsed) + 8), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    for i, segs in enumerate(parsed):
        x = 3
        for t, col in segs:
            x = tracked(d, (x, 3 + i * lh), t, f, col, tr)
    return im.crop(im.getbbox())


def chip(text, w=270, h=88):
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle([0, 0, w - 1, h - 1], radius=8, fill=(10, 16, 25, 200),
                        outline=(255, 255, 255, 46), width=1)
    d.text((24, 22), text, font=font("Inter.ttf", 26, "SemiBold"), fill=INK)
    d.line([(24, h - 30), (24 + 54, h - 30)], fill=ORANGE, width=3)
    return im


def logo():
    im = Image.new("RGBA", (420, 70), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle([0, 6, 30, 36], radius=4, fill=ORANGE)
    d.rounded_rectangle([8, 13, 22, 29], radius=2, outline=(30, 14, 4, 130), width=2)
    tracked(d, (42, 8), "TRAVEX", font("Inter.ttf", 26, "Bold"), INK, 5)
    tracked(d, (43, 44), "GLOBAL FORWARDING", font("JetBrainsMono.ttf", 9, "Medium"),
            (150, 160, 172), 4.6)
    return im.crop(im.getbbox())


# ---------------------------------------------------------------- frame
TITLE = text_layer(["Et si le fond", "n'était **pas une photo** ?"], 74, "Bold", lead=1.02)
LINE2 = text_layer(["Trois modes, deux continents, **un seul interlocuteur**."], 38, "Medium",
                   color=(214, 222, 231), tr=-1.0)
CHIPS = [chip("Aérien"), chip("Maritime"), chip("Ro-Ro")]
LOGO = logo()
CREDIT = text_layer(["Aucune photographie — tout est calculé image par image"], 22, "Regular",
                    color=(150, 162, 176), tr=0.2, fam="JetBrainsMono.ttf")


def frame(t, idx):
    im = BG.copy().convert("RGBA")
    im.alpha_composite(glow_at(t))
    im.alpha_composite(floor_grid(t))

    # particules qui montent
    for i in range(38):
        r = np.random.default_rng(i)
        x0, y0, sp = r.random(), r.random(), r.random()
        y = (y0 * H - t * (16 + 26 * sp)) % H
        x = (x0 * W + 22 * math.sin(t * (0.3 + 0.4 * sp) + i)) % W
        a = int(38 + 40 * sp)
        d = ImageDraw.Draw(im)
        d.ellipse([x - 1.6, y - 1.6, x + 1.6, y + 1.6], fill=(255, 238, 220, a))

    # phase 1 : titre      0.3 -> 3.6
    if t < 3.7:
        pin = ease((t - 0.3) / 0.9)
        pout = 1 - ease((t - 3.0) / 0.7)
        p = min(pin, pout)
        if p > 0:
            img = TITLE.copy()
            img.putalpha(Image.fromarray(
                (np.asarray(img.split()[-1], np.float32) * p).astype(np.uint8)))
            im.alpha_composite(img, (int(140), int(300 + 32 * (1 - pin) - 20 * (1 - pout))))

    # phase 2 : trajet      2.8 -> 8.8
    if 2.8 <= t < 8.9:
        prog = ease((t - 2.9) / 2.8)
        fade = 1 - ease((t - 8.1) / 0.8)
        lay = route_layer(prog)
        lay.putalpha(Image.fromarray(
            (np.asarray(lay.split()[-1], np.float32) * max(0, fade)).astype(np.uint8)))
        im.alpha_composite(lay)
        if t < 8.1:
            pl, xy = plane_at(prog)
            im.alpha_composite(pl, xy)
        d = ImageDraw.Draw(im)
        fm = font("JetBrainsMono.ttf", 17, "Medium")
        a1 = int(255 * ease((t - 3.0) / 0.6) * max(0, fade))
        if a1 > 0:
            tracked(d, (P0[0] - 78, P0[1] + 32), "RENCHEN · DE", fm, (255, 255, 255, a1), 4)
        a2 = int(255 * ease((t - 5.3) / 0.6) * max(0, fade))
        if a2 > 0:
            tracked(d, (P2[0] - 80, P2[1] - 56), "DOUALA · CM", fm, (255, 160, 107, a2), 4)

    # phase 3 : cartouches des modes   6.1 -> 9.4
    if t >= 6.1:
        for i, c in enumerate(CHIPS):
            pi = ease((t - 6.1 - i * 0.18) / 0.7)
            if pi <= 0:
                continue
            img = c.copy()
            img.putalpha(Image.fromarray(
                (np.asarray(img.split()[-1], np.float32) * pi).astype(np.uint8)))
            im.alpha_composite(img, (int(150 + i * 300), int(600 + 26 * (1 - pi))))

    # phase 4 : ligne + logo   7.2 -> 10
    if t >= 7.2:
        p = ease((t - 7.2) / 0.8)
        img = LINE2.copy()
        img.putalpha(Image.fromarray(
            (np.asarray(img.split()[-1], np.float32) * p).astype(np.uint8)))
        im.alpha_composite(img, (150, int(716 + 22 * (1 - p))))
        p2 = ease((t - 8.0) / 0.8)
        if p2 > 0:
            for obj, y in ((LOGO, 792), (CREDIT, 872)):
                o = obj.copy()
                o.putalpha(Image.fromarray(
                    (np.asarray(o.split()[-1], np.float32) * p2).astype(np.uint8)))
                im.alpha_composite(o, (150, y))

    # fondu d'entrée / sortie
    if t < 0.7:
        im = Image.blend(im, Image.new("RGBA", (W, H), (0, 0, 0, 255)), 1 - ease(t / 0.7))
    if t > DUR - 0.8:
        im = Image.blend(im, Image.new("RGBA", (W, H), (0, 0, 0, 255)),
                         ease((t - (DUR - 0.8)) / 0.8))

    # grain
    rng = np.random.default_rng(idx)
    g = (rng.normal(128, 14, (H, W, 1)).repeat(3, axis=2)).astype(np.uint8)
    im = Image.blend(im, Image.fromarray(g, "RGB").convert("RGBA"), 0.035)
    return im


def render():
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    total = int(DUR * FPS)
    cmd = [FFMPEG, "-y", "-hide_banner", "-loglevel", "error",
           "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
           "-c:v", "libx264", "-preset", "medium", "-crf", "19", "-pix_fmt", "yuv420p",
           "-movflags", "+faststart", OUT]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    for i in range(total):
        t = i / FPS
        proc.stdin.write(frame(t, i).convert("RGB").tobytes())
        if i % 60 == 0:
            print(f"  {i}/{total}", flush=True)
    proc.stdin.close()
    if proc.wait() != 0:
        raise SystemExit("ffmpeg a échoué")
    print("OK ->", OUT)


if __name__ == "__main__":
    render()
