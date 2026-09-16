#!/usr/bin/env python3
"""cutout_images.py — knock the matte out of the product photography.

Amway ships most packshots on a white or near-white card. 27 of the 65 have
real transparency and float on the film; the other 38 sit on a plate, and in
one grid you can see both. This removes the matte so every product floats.

How: flood fill inward from the border, so only background CONNECTED to the
edge is removed — white inside a label stays. A soft band at the boundary
keeps the cut edge from going jagged.

    python3 tools/cutout_images.py            # only what needs it
    python3 tools/cutout_images.py --all      # redo every product

Writes assets/products/<id>.webp (or .png where Pillow is missing) and
prints what it could not do cleanly.
NOTE: these are Amway's pixels, modified (matte removed) and served locally
rather than hot-linked, which Amway cleared for demo use.
"""
import os, struct, subprocess, sys, tempfile, urllib.request, zlib
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import sitedata                                        # noqa: E402
from tools.build_scaffold import SCENES, product_index  # noqa: E402

OUT = ROOT / "assets" / "products"
items = product_index(sitedata.load())
REDO = "--all" in sys.argv

NEAR = 26      # within this of the background colour: definitely matte
FAR = 74       # beyond this: definitely product. between the two: soft edge
MAX = 480      # a card is ~170 CSS px; 480 covers a 2-3x phone and caps the
               # oversized 690px sources, which are pure weight at this size
QUALITY = 85   # webp with alpha. At 3x zoom on the smallest packshot type
               # this is indistinguishable from the PNG, at a sixth the bytes.

try:
    from PIL import Image
except ImportError:                              # falls back to PNG, ~6x bigger
    Image = None


def to_bmp(b):
    """sips writes a real BMP for most sources but, for some, headerless raw
    pixels. Ask it for the dimensions so both can be read."""
    d = tempfile.mkdtemp()
    src, dst = os.path.join(d, "s"), os.path.join(d, "s.bmp")
    try:
        with open(src, "wb") as f:
            f.write(b)
        # resize first, so the dimensions queried match the pixels written
        subprocess.run(["sips", "-Z", str(MAX), "-s", "format", "png",
                        src, "--out", src + ".png"], capture_output=True)
        if os.path.exists(src + ".png"):
            src = src + ".png"
        g = subprocess.run(["sips", "-g", "pixelWidth", "-g", "pixelHeight", src],
                           capture_output=True, text=True)
        dim = {}
        for line in g.stdout.splitlines():
            if ":" in line:
                k, v = line.rsplit(":", 1)
                dim[k.strip()] = v.strip()
        try:
            wh = (int(dim["pixelWidth"]), int(dim["pixelHeight"]))
        except (KeyError, ValueError):
            wh = None
        r = subprocess.run(["sips", "-s", "format", "bmp", src, "--out", dst],
                           capture_output=True)
        if r.returncode == 0 and os.path.exists(dst):
            with open(dst, "rb") as f:
                return f.read(), wh
    finally:
        for f in (src, src + ".png", dst, os.path.join(d, "s")):
            if os.path.exists(f):
                os.remove(f)
        if os.path.isdir(d):
            os.rmdir(d)
    return None, None


def _shift(mask):
    if not mask:
        return 0, 0
    s = 0
    while not (mask >> s) & 1:
        s += 1
    return s, mask >> s


def read_raw(d, wh):
    """Headerless pixel dump: exactly w*h*3 (RGB) or w*h*4 (RGBA), top-down."""
    if not wh:
        return None
    w, h = wh
    for n in (3, 4):
        if len(d) == w * h * n:
            px = bytearray(w * h * 3)
            sa = bytearray(b"\xff" * (w * h))
            for i in range(w * h):
                px[i * 3] = d[i * n]
                px[i * 3 + 1] = d[i * n + 1]
                px[i * 3 + 2] = d[i * n + 2]
                if n == 4:
                    sa[i] = d[i * 4 + 3]
            return w, h, px, sa
    return None


def read_bmp(d, wh=None):
    """24-bit BI_RGB, and 32-bit BI_BITFIELDS as sips writes for RGBA
    sources. Returns RGB plus whatever alpha the source already carried."""
    if d[:2] != b"BM":
        return read_raw(d, wh)
    off = struct.unpack("<I", d[10:14])[0]
    dib = struct.unpack("<I", d[14:18])[0]
    w, h, _planes, bpp, comp = struct.unpack("<iiHHI", d[18:34])
    if bpp not in (24, 32) or comp not in (0, 3):
        return None
    top_down = h < 0
    h = abs(h)
    n = bpp // 8
    stride = (w * n + 3) & ~3
    px = bytearray(w * h * 3)
    sa = bytearray(b"\xff" * (w * h))

    if bpp == 32 and comp == 3 and dib >= 56:
        rm, gm, bm, am = struct.unpack("<IIII", d[54:70])
    else:
        rm, gm, bm, am = 0x00FF0000, 0x0000FF00, 0x000000FF, (0xFF000000 if bpp == 32 else 0)
    rs, _ = _shift(rm); gs, _ = _shift(gm); bs, _ = _shift(bm); as_, _ = _shift(am)

    for y in range(h):
        sy = y if top_down else h - 1 - y
        row = d[off + sy * stride: off + sy * stride + w * n]
        o, a = y * w * 3, y * w
        if bpp == 24:
            for x in range(w):                   # BMP is BGR
                px[o + x * 3] = row[x * 3 + 2]
                px[o + x * 3 + 1] = row[x * 3 + 1]
                px[o + x * 3 + 2] = row[x * 3]
        else:
            for x in range(w):
                v = struct.unpack_from("<I", row, x * 4)[0]
                px[o + x * 3] = (v & rm) >> rs
                px[o + x * 3 + 1] = (v & gm) >> gs
                px[o + x * 3 + 2] = (v & bm) >> bs
                if am:
                    sa[a + x] = (v & am) >> as_
    return w, h, px, sa


def write_png(path, w, h, rgb, alpha):
    """Adaptive row filtering — the standard minimum-sum-of-absolute-
    differences heuristic. On photographic RGBA this is worth roughly a
    third of the file over filter 0, for nothing but a little arithmetic."""
    stride = w * 4
    lines = []
    for y in range(h):
        line = bytearray(stride)
        o, a = y * w * 3, y * w
        for x in range(w):
            line[x * 4] = rgb[o + x * 3]
            line[x * 4 + 1] = rgb[o + x * 3 + 1]
            line[x * 4 + 2] = rgb[o + x * 3 + 2]
            line[x * 4 + 3] = alpha[a + x]
        lines.append(line)

    raw = bytearray()
    prev = bytearray(stride)
    for line in lines:
        best, best_f, best_score = None, 0, None
        for f in range(5):
            out = bytearray(stride)
            for i in range(stride):
                a = line[i - 4] if i >= 4 else 0
                b = prev[i]
                c = prev[i - 4] if i >= 4 else 0
                if f == 0:
                    v = line[i]
                elif f == 1:
                    v = line[i] - a
                elif f == 2:
                    v = line[i] - b
                elif f == 3:
                    v = line[i] - (a + b) // 2
                else:
                    pa, pb, pc = abs(b - c), abs(a - c), abs(a + b - 2 * c)
                    pr = a if (pa <= pb and pa <= pc) else (b if pb <= pc else c)
                    v = line[i] - pr
                out[i] = v & 255
            score = sum(x if x < 128 else 256 - x for x in out)
            if best_score is None or score < best_score:
                best, best_f, best_score = out, f, score
        raw.append(best_f)
        raw += best
        prev = line

    def chunk(t, data):
        c = t + data
        return struct.pack(">I", len(data)) + c + struct.pack(">I", zlib.crc32(c))

    png = (b"\x89PNG\r\n\x1a\n"
           + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0))
           + chunk(b"IDAT", zlib.compress(bytes(raw), 9))
           + chunk(b"IEND", b""))
    path.write_bytes(png)


def cut(w, h, px):
    """Flood fill the border-connected matte. Returns alpha, coverage."""
    def at(i):
        o = i * 3
        return px[o], px[o + 1], px[o + 2]

    corners = [at(0), at(w - 1), at((h - 1) * w), at(h * w - 1)]
    br = sum(c[0] for c in corners) // 4
    bg_g = sum(c[1] for c in corners) // 4
    bb = sum(c[2] for c in corners) // 4

    alpha = bytearray(b"\xff" * (w * h))
    seen = bytearray(w * h)
    q = deque()
    for x in range(w):
        q.append(x); q.append((h - 1) * w + x)
    for y in range(h):
        q.append(y * w); q.append(y * w + w - 1)

    while q:
        i = q.popleft()
        if seen[i]:
            continue
        seen[i] = 1
        o = i * 3
        d = abs(px[o] - br) + abs(px[o + 1] - bg_g) + abs(px[o + 2] - bb)
        if d >= FAR:
            continue                             # product: stop here
        if d <= NEAR:
            alpha[i] = 0
        else:                                    # soft boundary, do not spread
            alpha[i] = int(255 * (d - NEAR) / (FAR - NEAR))
            continue
        x, y = i % w, i // w
        if x: q.append(i - 1)
        if x < w - 1: q.append(i + 1)
        if y: q.append(i - w)
        if y < h - 1: q.append(i + w)

    kept = sum(1 for v in alpha if v)
    return alpha, kept / (w * h)


def existing(pid):
    for ext in ("webp", "png"):
        f = OUT / ("%s.%s" % (pid, ext))
        if f.exists():
            return f
    return None


def run(pid):
    if not REDO and existing(pid):
        return pid, None
    try:
        b = urllib.request.urlopen(items[pid]["img"], timeout=40).read()
    except Exception as e:
        return pid, "fetch failed (re-run to retry): %s" % str(e)[:34]
    bmp, wh = to_bmp(b)
    if bmp is None:
        return pid, "could not rasterise"
    r = read_bmp(bmp, wh)
    if r is None:
        return pid, "unexpected bitmap"
    w, h, px, src_a = r
    alpha, cover = cut(w, h, px)
    for i in range(w * h):                       # never add back what was cut
        if src_a[i] < alpha[i]:
            alpha[i] = src_a[i]
    cover = sum(1 for v in alpha if v) / (w * h)
    if cover > 0.92:
        return pid, "no matte found (%.0f%% opaque) — left alone" % (cover * 100)
    if cover < 0.04:
        return pid, "would erase the product (%.1f%% left) — left alone" % (cover * 100)
    if Image is not None:
        im = Image.frombytes("RGB", (w, h), bytes(px)).convert("RGBA")
        im.putalpha(Image.frombytes("L", (w, h), bytes(alpha)))
        im.save(OUT / ("%s.webp" % pid), format="WEBP",
                quality=QUALITY, method=6)
    else:
        write_png(OUT / ("%s.png" % pid), w, h, px, alpha)
    return pid, None


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    ids = [p for sc in SCENES for _, i in sc["clusters"] for p in i]
    with ThreadPoolExecutor(6) as ex:
        res = list(ex.map(run, ids))
    ok = [p for p, e in res if e is None]
    bad = [(p, e) for p, e in res if e]
    print("cut out %d of %d  ->  assets/products/" % (len(ok), len(ids)))
    for p, e in bad:
        print("   %-8s %-44s %s" % (p, items[p]["name"][:42], e))


if __name__ == "__main__":
    main()
