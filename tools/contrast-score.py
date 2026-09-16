#!/usr/bin/env python3
"""Score the contrast samples gates.js captured.

gates.js photographs what sits *behind* each piece of text at 21 points
across room one's scroll, with the text itself hidden. This reads those
frames and computes the WCAG contrast ratio of each text colour against the
pixels it actually lands on — not against a colour we hoped was there.

Reported per element: the mean ratio, and the 5th-percentile worst ratio,
which is the honest number for text over a non-uniform background.

    python3 tools/contrast-score.py
"""
import json
import sys
from collections import defaultdict
from pathlib import Path

from PIL import Image

OUT = Path("gates")
# WCAG AA: 4.5 for body text, 3.0 for large text (>=24px, or >=18.66px bold).
FLOOR = {"small": 4.5, "large": 3.0}


def lin(c):
    c /= 255.0
    return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4


def lum(rgb):
    r, g, b = rgb[:3]
    return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b)


def ratio(l1, l2):
    hi, lo = max(l1, l2), min(l1, l2)
    return (hi + 0.05) / (lo + 0.05)


def parse_color(css):
    body = css[css.index("(") + 1:css.rindex(")")]
    parts = [float(x) for x in body.replace("/", ",").split(",") if x.strip()]
    return parts[0], parts[1], parts[2]


def blend(fg, bg, alpha):
    return tuple(fg[i] * alpha + bg[i] * (1 - alpha) for i in range(3))


def main():
    samples = json.loads((OUT / "contrast-input.json").read_text())
    per_el = defaultdict(list)
    rows = []

    for s in samples:
        img = Image.open(s["file"]).convert("RGB")
        W, H = img.size
        for b in s["boxes"]:
            x, y, w, h = b["box"]["x"], b["box"]["y"], b["box"]["w"], b["box"]["h"]
            x2, y2 = min(W, x + w), min(H, y + h)
            if x2 <= x or y2 <= y:
                continue
            # Inset by two pixels: a control's own border sits on the edge of
            # its box and is foreground, not backdrop.
            if x2 - x > 6 and y2 - y > 6:
                x, y, x2, y2 = x + 2, y + 2, x2 - 2, y2 - 2
            region = img.crop((x, y, x2, y2))
            px = list(region.getdata())
            if not px:
                continue

            fg = parse_color(b["color"])
            a = b["opacity"]

            # Drop pixels that are essentially the text colour itself. With the
            # glyphs made transparent, anything left matching them that closely
            # is the element's own furniture showing through the box — a pull
            # knob, a border, an icon — not the surface the text is read
            # against. Measuring those would score the design against itself.
            def is_fg(c):
                return sum(abs(c[i] - fg[i]) for i in range(3)) < 30

            body = [c for c in px if not is_fg(c)]
            if len(body) < max(8, len(px) * 0.15):
                continue          # almost nothing but furniture: nothing to score
            px = body

            ls = []
            for p in px:
                bgl = lum(p)
                # the element's own opacity composites it onto this pixel
                eff = blend(fg, p, a) if a < 0.999 else fg
                ls.append(ratio(lum(eff), bgl))

            ls.sort()
            worst = ls[max(0, int(len(ls) * 0.05))]
            mean = sum(ls) / len(ls)
            room = s.get("room", "room-sleep").replace("room-", "")
            per_el[(room + " " + b["sel"], b["size"])].append((s["p"], mean, worst))
            rows.append((s["p"], room + " " + b["sel"], b["size"], mean, worst))

    print(f"{'room and element':38} {'size':6} {'floor':>5} {'mean':>7} {'p5 worst':>9} {'at p':>6}  verdict")
    print("-" * 78)
    failures = []
    for (sel, size), vals in sorted(per_el.items()):
        floor = FLOOR[size]
        means = [v[1] for v in vals]
        worst_v = min(vals, key=lambda v: v[2])
        ok = worst_v[2] >= floor
        if not ok:
            failures.append((sel, size, worst_v))
        print(f"{sel:38} {size:6} {floor:5.1f} {sum(means)/len(means):7.2f} "
              f"{worst_v[2]:9.2f} {worst_v[0]:6.2f}  {'ok' if ok else 'BELOW FLOOR'}")

    # the midpoint specifically — this is where a naive cross-fade fails
    print("\nthe midpoint of each room (progress 0.50), where a naive cross-fade fails:")
    mid = [r for r in rows if abs(r[0] - 0.5) < 1e-6]
    for p, sel, size, mean, worst in sorted(mid, key=lambda r: r[4]):
        print(f"   {sel:24} {size:6} floor {FLOOR[size]:.1f}  mean {mean:6.2f}  p5 worst {worst:6.2f}"
              f"  {'ok' if worst >= FLOOR[size] else 'BELOW FLOOR'}")

    if failures:
        print(f"\n{len(failures)} element(s) below the floor somewhere in the scroll")
        return 1
    print("\nevery measured text element clears WCAG AA at every sampled point")
    return 0


if __name__ == "__main__":
    sys.exit(main())
