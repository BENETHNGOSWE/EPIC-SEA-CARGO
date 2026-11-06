#!/usr/bin/env python3
"""brand_assets.py — turn the one supplied logo file into everything the site needs.

The logo arrived as a JPEG on white, so the first job is knocking that white out (and
un-blending the edge pixels so nothing gets a halo). From there: a full-colour mark for the
light header, a light version for the dark footer, favicons, and an og:image.

    python3 brand_assets.py          # re-run whenever the logo file changes
    inputs   wp-content/uploads/brand/epic-sea-cargo.jpg
    outputs  logo.webp/.png  logo-footer.webp/.png  mark-*.png  favicon-*.png
             apple-touch-icon.png  og-image.jpg
build_site.py calls main() automatically if a derived file is missing, so a normal
`python3 build_site.py` regenerates them after the logo is swapped.
"""
import os, sys
import numpy as np
from PIL import Image

ROOT = os.path.dirname(os.path.abspath(__file__))
DIR = os.path.join(ROOT, "wp-content/uploads/brand")
SRC = os.path.join(DIR, "epic-sea-cargo.jpg")
NAVY = np.array([1, 49, 115], float)          # #013173, sampled from the artwork
RED = np.array([163, 0, 43], float)           # #A3002B
WHITE = np.array([255, 255, 255], float)
LIGHT_RED = np.array([255, 122, 133], float)  # the red, lifted so it reads on navy


def knock_out(im):
    """Flat artwork on white: alpha from how far the pixel is from white, then un-premultiply
    so the surviving colour is the true ink rather than a white-washed edge."""
    a = np.asarray(im.convert("RGB")).astype(float)
    alpha = np.clip((255.0 - a.min(2)) / 255.0, 0, 1)
    alpha[alpha < 0.08] = 0.0                             # near-white really is background
    safe = np.where(alpha[..., None] > 0, alpha[..., None], 1.0)
    fg = np.clip((a - 255.0 * (1 - alpha[..., None])) / safe, 0, 255)
    return Image.fromarray(np.dstack([fg, alpha * 255]).astype("uint8"), "RGBA")


def trim(im, pad_frac=0.02):
    al = np.asarray(im)[..., 3]
    ys, xs = np.where(al > 12)
    if len(xs) == 0:
        return im
    x0, y0, x1, y1 = xs.min(), ys.min(), xs.max() + 1, ys.max() + 1
    pad = int(round((x1 - x0) * pad_frac))
    W, H = im.size
    return im.crop((max(0, x0 - pad), max(0, y0 - pad), min(W, x1 + pad), min(H, y1 + pad)))


def mark_only(im):
    """The symbol above the wordmark, for favicons: the widest run of empty rows splits them."""
    al = np.asarray(im)[..., 3]
    rows = np.where((al > 20).sum(1) > 0)[0]
    if len(rows) < 8:
        return im
    w = float(al.shape[1])
    ink = np.asarray((al > 20).sum(1), float)
    band = max(2, int(im.size[1] * 0.05))
    lo, hi = int(im.size[1] * 0.30), int(im.size[1] * 0.92)
    best, at = None, None
    for y in range(max(rows[0], lo), max(hi, rows[0] + 1) - band):
        total = ink[y:y + band].mean() / w
        if best is None or total < best:
            best, at = total, y
    if best is not None and best < 0.10:                      # a genuinely quiet seam
        return im.crop((0, 0, im.size[0], at))
    return im


def scale_to(im, h):
    w = max(1, int(round(im.size[0] * h / im.size[1])))
    return im.resize((w, h), Image.LANCZOS)


def to_footer(im):
    """On the navy footer, ink becomes white and the red stripe becomes a lifted red,
    blended per pixel so the anti-aliasing survives."""
    a = np.asarray(im).astype(float)
    rgb, alpha = a[..., :3], a[..., 3:]
    dn = np.linalg.norm(rgb - NAVY, axis=2)
    dr = np.linalg.norm(rgb - RED, axis=2)
    t = dn / np.maximum(dn + dr, 1e-6)                       # 0 = navy-ish, 1 = red-ish
    new = WHITE * (1 - t[..., None]) + LIGHT_RED * t[..., None]
    keep = alpha / 255.0
    new = new * keep + np.array([1, 49, 115], float) * (1 - keep)   # keep the footer bg in the halo
    return Image.fromarray(np.dstack([np.clip(new, 0, 255), alpha[..., 0]]).astype("uint8"), "RGBA")


def tile(im, size, bg=255, pad=0.16):
    """Centre a mark in a square tile with breathing room — what a favicon needs."""
    out = Image.new("RGBA", (size, size), (bg, bg, bg, 255) if bg is not None else (0, 0, 0, 0))
    h = int(round(size * (1 - 2 * pad)))
    m = scale_to(im, h)
    if m.size[0] > size - 2 * int(size * pad):
        m = m.resize((size - 2 * int(size * pad), max(1, int(round(m.size[1] * (size - 2 * int(size * pad)) / m.size[0])))), Image.LANCZOS)
    out.alpha_composite(m, ((size - m.size[0]) // 2, (size - m.size[1]) // 2))
    return out


def save(im, stem, jpeg=False):
    base = os.path.join(DIR, stem)
    if jpeg:
        bg = Image.new("RGB", im.size, (255, 255, 255))
        bg.paste(im.convert("RGBA"), mask=im.convert("RGBA"))
        bg.save(base + ".jpg", "JPEG", quality=86, optimize=True)
        return base + ".jpg", os.path.getsize(base + ".jpg")
    im.save(base + ".png", "PNG", optimize=True)
    try:
        # keep the alpha channel - converting to RGB first filled every knocked-out pixel
        # with black and the logo arrived in the browser wearing a black box
        im.save(base + ".webp", "WEBP", quality=92, method=6)
    except Exception:
        pass
    return base + ".png", os.path.getsize(base + ".png")


def main(quiet=False):
    if not os.path.exists(SRC):
        print(f"  brand: {os.path.relpath(SRC, ROOT)} not found - leaving the demo logo in place")
        return None
    full = trim(knock_out(Image.open(SRC)))
    info = {}
    for stem, img, kw in (
        ("logo", scale_to(full, 252), {}),                        # header, 2x of 126px tall
        ("logo-footer", to_footer(scale_to(full, 238)), {}),      # footer, 2x of 119px tall
        ("mark", scale_to(mark_only(full), 252), {}),
        ("favicon-32", tile(mark_only(full), 32), {}),
        ("favicon-192", tile(mark_only(full), 192), {}),
        ("apple-touch-icon", tile(mark_only(full), 180), {}),
        ("og-image", tile(full, 630, bg=None), {}),
    ):
        if stem == "og-image":
            big = Image.new("RGB", (1200, 630), (255, 255, 255))
            m = scale_to(full, int(630 * 0.62))
            big.paste(m.convert("RGB"), ((1200 - m.size[0]) // 2, (630 - m.size[1]) // 2), m)
            p = os.path.join(DIR, "og-image.jpg")
            big.save(p, "JPEG", quality=88, optimize=True)
            info[stem] = (big.size, os.path.getsize(p))
            continue
        p, n = save(img, stem)
        info[stem] = (img.size, n)
    if not quiet:
        print("  brand: derived from epic-sea-cargo.jpg -> " +
              ", ".join(f"{k} {v[0][0]}x{v[0][1]} ({v[1] / 1024:.0f} KB)" for k, v in info.items()))
    return info


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
