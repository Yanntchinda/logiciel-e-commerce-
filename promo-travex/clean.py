#!/usr/bin/env python3
"""
Nettoie un filigrane dans un clip généré (Kling, Hailuo, Runway, Pika…).

Deux méthodes, dans cet ordre de préférence :

1. --zoom 1.12   recadre le cadre : un logo collé dans un angle sort du champ.
                 Rapide, invisible, aucun calcul de reconstruction.
2. --box X,Y,W,H reconstruit le fond sous le logo (inpainting OpenCV), image par
                 image, uniquement dans la zone concernée. Pour un logo centré ou
                 trop gros pour être recadré.

Exemples
    python3 promo-travex/clean.py --in clip.mp4 --out clip_clean.mp4 --zoom 1.12
    python3 promo-travex/clean.py --in clip.mp4 --out clip_clean.mp4 --box 1620,1000,280,60
    python3 promo-travex/clean.py --in clips/ --out clips_clean/ --zoom 1.12
"""
import os, re, sys, glob, argparse, subprocess, tempfile
import numpy as np
import cv2
import imageio_ffmpeg

FF = imageio_ffmpeg.get_ffmpeg_exe()


def probe(path):
    """(largeur, hauteur, fps) via le flux d'erreurs de ffmpeg."""
    p = subprocess.run([FF, "-hide_banner", "-i", path], capture_output=True, text=True)
    txt = p.stderr
    m = re.search(r"Video:.*?(\d{2,5})x(\d{2,5})", txt)
    if not m:
        raise RuntimeError(f"impossible de lire {path}")
    w, h = int(m.group(1)), int(m.group(2))
    f = re.search(r"([\d.]+) fps", txt)
    fps = float(f.group(1)) if f else 30.0
    return w, h, fps


def pad_box(box, w, h, margin=10):
    x, y, bw, bh = box
    return (max(0, x - margin), max(0, y - margin),
            min(w, x + bw + margin), min(h, y + bh + margin))


def build_mask(x0, y0, x1, y1, box, feather=6, grow=4):
    """Masque binaire (agrandi) + alpha adouci pour la couture."""
    roi_w, roi_h = x1 - x0, y1 - y0
    mask = np.zeros((roi_h, roi_w), np.uint8)
    bx0, by0 = box[0] - x0, box[1] - y0
    cv2.rectangle(mask, (bx0, by0), (bx0 + box[2], by0 + box[3]), 255, -1)
    if grow:
        k = np.ones((grow * 2 + 1, grow * 2 + 1), np.uint8)
        mask = cv2.dilate(mask, k)
    if feather:
        alpha = cv2.GaussianBlur(mask, (0, 0), feather).astype(np.float32) / 255.0
        alpha = np.clip(alpha * 1.6, 0, 1)
    else:
        alpha = (mask > 0).astype(np.float32)
    return mask, alpha


def process(src, dst, zoom=1.0, box=None, radius=6, keep_audio=True):
    w, h, fps = probe(src)
    out_w, out_h = int(w / zoom) // 2 * 2, int(h / zoom) // 2 * 2
    ox, oy = (w - out_w) // 2, (h - out_h) // 2

    mask = alpha = None
    if box:
        x0, y0, x1, y1 = pad_box(box, w, h)
        mask, alpha = build_mask(x0, y0, x1, y1, box)
        print(f"  inpainting zone {box} (marge {x0},{y0} → {x1},{y1})")
    if zoom > 1.0:
        print(f"  recadrage x{zoom:.2f} → {out_w}x{out_h}")

    dec = subprocess.Popen([FF, "-hide_banner", "-loglevel", "error", "-i", src,
                            "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                           stdout=subprocess.PIPE)

    cmd = [FF, "-y", "-hide_banner", "-loglevel", "error",
           "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{w}x{h}", "-r", str(fps), "-i", "-"]
    if keep_audio:
        cmd += ["-i", src, "-map", "0:v", "-map", "1:a?", "-c:a", "aac", "-b:a", "160k"]
    cmd += ["-vf", f"crop={out_w}:{out_h}:{ox}:{oy}" if zoom > 1.0 else "null",
            "-c:v", "libx264", "-preset", "medium", "-crf", "18",
            "-pix_fmt", "yuv420p", "-movflags", "+faststart", dst]
    enc = subprocess.Popen(cmd, stdin=subprocess.PIPE)

    frame_bytes = w * h * 3
    n = 0
    while True:
        buf = dec.stdout.read(frame_bytes)
        if len(buf) < frame_bytes:
            break
        frame = np.frombuffer(buf, np.uint8).reshape(h, w, 3).copy()
        if mask is not None:
            roi = frame[y0:y1, x0:x1]
            clean = cv2.inpaint(roi, mask, radius, cv2.INPAINT_TELEA)
            a = alpha[..., None]
            frame[y0:y1, x0:x1] = (roi.astype(np.float32) * (1 - a) +
                                   clean.astype(np.float32) * a).astype(np.uint8)
        enc.stdin.write(frame.tobytes())
        n += 1

    enc.stdin.close()
    dec.stdout.close()
    dec.wait()
    if enc.wait() != 0:
        raise SystemExit("ffmpeg (encodage) a échoué")
    print(f"  {n} images → {dst}")


def main():
    ap = argparse.ArgumentParser(description="Nettoyage de filigrane")
    ap.add_argument("--in", dest="src", required=True, help="clip ou dossier")
    ap.add_argument("--out", dest="dst", required=True, help="clip ou dossier de sortie")
    ap.add_argument("--zoom", type=float, default=1.0, help="recadrage (1.12 conseillé)")
    ap.add_argument("--box", default="", help="X,Y,W,H de la zone à reconstruire")
    ap.add_argument("--radius", type=int, default=8, help="rayon d'inpainting")
    ap.add_argument("--no-audio", action="store_true")
    a = ap.parse_args()

    box = None
    if a.box:
        parts = [int(float(v)) for v in a.box.replace(" ", "").split(",")]
        if len(parts) != 4:
            raise SystemExit("--box attend X,Y,W,H")
        box = tuple(parts)

    if os.path.isdir(a.src):
        os.makedirs(a.dst, exist_ok=True)
        files = sorted(sum([glob.glob(os.path.join(a.src, e))
                            for e in ("*.mp4", "*.mov", "*.m4v", "*.webm")], []))
        if not files:
            raise SystemExit("aucun clip trouvé")
        for f in files:
            print(os.path.basename(f))
            process(f, os.path.join(a.dst, os.path.basename(f)), a.zoom, box,
                    a.radius, not a.no_audio)
    else:
        print(os.path.basename(a.src))
        process(a.src, a.dst, a.zoom, box, a.radius, not a.no_audio)


if __name__ == "__main__":
    main()
