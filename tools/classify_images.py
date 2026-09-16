#!/usr/bin/env python3
"""classify_images.py — decide how each product image wants to be shown.

Writes image-kinds.tsv:   <id>\t<cut|photo|white>\t<chosen url>

  cut    real transparency — the product floats on the film, no plate
  photo  an opaque photograph — framed edge to edge, as a photograph
  white  a packshot matted on white — softened at the edge so the rectangle
         dissolves into the film instead of sitting on it as a chip

Each product is judged on BOTH the pinned lead image and its second
photograph from hover-images.tsv, and the better of the two wins. That is
the data layer doing its job: five products carry a real photograph in
hover-images.tsv where the lead is matted on white.

Network-bound, so the result is cached to the .tsv and the build reads that.
Re-run only when lead-images.tsv changes.

    python3 tools/classify_images.py
"""
import os, struct, subprocess, sys, tempfile, urllib.request, zlib
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import sitedata                                   # noqa: E402
from tools.build_scaffold import SCENES, product_index   # noqa: E402

OUT = ROOT / "image-kinds.tsv"
_d = sitedata.load()
items = product_index(_d)
HOVER = _d["hover"]


def first_row(b):
    """Decode scanline 0 only — enough to read the top corners."""
    if b[:8] != b"\x89PNG\r\n\x1a\n":
        return None
    i, w, depth, ctype, idat, plte = 8, 0, 0, 0, b"", b""
    while i < len(b):
        ln = struct.unpack(">I", b[i:i + 4])[0]
        typ, data = b[i + 4:i + 8], b[i + 8:i + 8 + ln]
        if typ == b"IHDR":
            w, _h, depth, ctype = struct.unpack(">IIBB", data[:10])
        elif typ == b"PLTE":
            plte = data
        elif typ == b"IDAT":
            idat += data
        elif typ == b"IEND":
            break
        i += 12 + ln
    if depth != 8 or ctype not in (2, 3, 6) or not w:
        return None
    ch = {2: 3, 3: 1, 6: 4}[ctype]
    stride = w * ch
    raw = zlib.decompressobj().decompress(idat, stride + 1)
    if len(raw) < stride + 1:
        return None
    f, line = raw[0], bytearray(raw[1:stride + 1])
    if f in (1, 3, 4):                       # Sub / Avg / Paeth vs a zero prior row
        for k in range(ch, stride):
            a = line[k - ch]
            line[k] = (line[k] + (a if f == 1 else a // 2 if f == 3 else a)) & 255

    def px(n):
        o = n * ch
        if ctype == 3:
            p = line[o] * 3
            return (plte[p], plte[p + 1], plte[p + 2], 255)
        if ctype == 2:
            return (line[o], line[o + 1], line[o + 2], 255)
        return (line[o], line[o + 1], line[o + 2], line[o + 3])

    return px(1), px(w - 2)


RANK = {"cut": 0, "photo": 1, "white": 2, "none": 3}


def to_png(b):
    """A JPEG cannot carry alpha, but it can still be matted on white, and
    that is what decides the treatment. sips ships with macOS."""
    d = tempfile.mkdtemp()
    src, dst = os.path.join(d, "s"), os.path.join(d, "s.png")
    try:
        with open(src, "wb") as f:
            f.write(b)
        r = subprocess.run(["sips", "-s", "format", "png", src, "--out", dst],
                           capture_output=True)
        if r.returncode == 0 and os.path.exists(dst):
            with open(dst, "rb") as f:
                return f.read()
    except Exception:
        pass
    finally:
        for f in (src, dst):
            if os.path.exists(f):
                os.remove(f)
        os.rmdir(d)
    return None


def classify(url):
    if not url:
        return "none"
    try:
        b = urllib.request.urlopen(url, timeout=30).read()
    except Exception:
        return "none"
    if b[:8] != b"\x89PNG\r\n\x1a\n":
        b = to_png(b)                        # JPEG: transcode so the same test applies
        if b is None:
            return "photo"
    r = first_row(b)
    if r is None:
        return "photo"
    a, c = r
    if a[3] < 16 and c[3] < 16:
        return "cut"
    if min(a[:3]) > 246 and min(c[:3]) > 246:
        return "white"
    return "photo"


def best(pid):
    """The pinned lead image wins almost always. hover-images.tsv is NOT a
    second photograph of the same product — a good number of those rows are
    marketing comparison charts, and two different flavours can share one.
    So the only swap allowed is to a genuine cut-out: strictly better, and
    a chart never qualifies."""
    lead = items[pid]["img"]
    kl = classify(lead)
    if kl != "cut":
        alt = HOVER.get(pid, "")
        if alt and classify(alt) == "cut":
            return pid, "cut", alt, True
    return pid, (kl if kl != "none" else "photo"), lead, False


def main():
    ids = [p for sc in SCENES for _, i in sc["clusters"] for p in i]
    with ThreadPoolExecutor(12) as ex:
        rows = list(ex.map(best, ids))
    OUT.write_text(
        "# how each product image wants to be shown, and which photograph won.\n"
        "# id <tab> cut|photo|white <tab> url    — tools/classify_images.py\n"
        + "".join("%s\t%s\t%s\n" % (p, k, u) for p, k, u, _ in rows),
        encoding="utf-8")
    c = {k: sum(1 for _, kk, _, _ in rows if kk == k) for k in ("cut", "photo", "white")}
    sw = [(p, items[p]["name"]) for p, _, _, s in rows if s]
    print("image-kinds.tsv  %d images  ·  %d cut  ·  %d photo  ·  %d white"
          % (len(rows), c["cut"], c["photo"], c["white"]))
    if sw:
        print("\nswapped to the hover photograph (lead was matted on white):")
        for p, n in sw:
            print("   %-8s %s" % (p, n[:58]))


if __name__ == "__main__":
    main()
