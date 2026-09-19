#!/usr/bin/env python3
"""build_pour.py — put the data layer into proto/pour.html.

    python3 tools/build_pour.py

The page is written by hand; this only replaces what sits between the
/*DATA*/ and /*END DATA*/ markers: every product (name, share-link, image),
the five rooms from rooms.tsv, and the quiz. Products are read through
sitedata.py like every other build, never retyped, so share-links survive.

The quiz lives here as data: each goal names the products that answer it,
best first. Scoring in the page only reorders and filters these lists — it
never recommends a product nobody picked for that goal.
"""
import html, json, re, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "tools"))
import sitedata                      # noqa: E402
import build_scaffold as scaffold    # noqa: E402

PAGE = ROOT / "proto" / "pour.html"

ROOMS = [
    ("sunrise",  "Sunrise Stack",      "What the day starts on."),
    ("protein",  "Protein Snack Pack", "Protein in every form you'll actually eat."),
    ("energy",   "Energy Elevation",   "XS, and what goes before the session."),
    ("recovery", "Recovery Room",      "After the session, and after dark."),
    ("skin",     "Skin Redefined",     "Skin, fed from the inside."),
]

# goal key, label, products best first, the reason shown on a pick
GOALS = [
    ("energy",   "More energy",    ["266673", "126883", "101593", "126983"],
     "Clean energy without the sugar crash."),
    ("focus",    "Sharper focus",  ["266673", "107846", "101593"],
     "Caffeine plus focus nutrients for the afternoon slump."),
    ("sleep",    "Better sleep",   ["127940", "124506", "128032", "308636"],
     "Winds the day down so the night can do its work."),
    ("stress",   "Less stress",    ["308641", "308636", "296753"],
     "Adaptogens and calm for a nervous system that's been on all day."),
    ("gut",      "Gut health",     ["127725", "120571"],
     "Fibre, pre- and probiotics: the base everything else sits on."),
    ("strength", "Build strength", ["128156", "128463", "126753", "316375"],
     "Protein and creatine to turn training into muscle."),
    ("recovery", "Recover faster", ["316379", "300323", "110601"],
     "Refuel, rehydrate, and ease what's sore."),
    ("skin",     "Skin and glow",  ["123783V", "125575", "124812"],
     "Nutrition for skin, from the inside out."),
    ("hydrate",  "Hydration",      ["110601", "110631", "110922"],
     "Electrolytes that make water work harder."),
    ("snacks",   "Smarter snacks", ["110385", "316302", "110627", "110370"],
     "Protein that fits in a bag and tastes like a treat."),
]

FORMAT_RULES = [            # first match wins
    ("topical", r"\bCream\b"),
    ("snack",   r"\bBars?\b|\bCrisps\b"),
    ("capsule", r"Capsules|Gummies|Tablets|Probiotic|Magnesium|Sleep Health|Skin|Glow|Beauty|Collagen"),
    ("drink",   r"12 oz|Shakes|\bTea\b|Energy Drink|Juiced"),
    ("powder",  r"."),
]
CAFFEINE_FREE = re.compile(r"Caffeine Free|Protein|Whey|Bars|Crisps|Cream|Sleep|Magnesium|Ashwagandha|"
                           r"Chamomile|Probiotic|GI Primer|Creatine|Twist Tubes|CocoWater|Recovery|"
                           r"Multiplier|Skin|Glow|Sweet Dreams", re.I)


def short(name):
    """'XS™ Grass-Fed Whey Protein – Vanilla' -> brand and product, for a card."""
    name = name.replace("–", "-").replace("—", "-")
    m = re.match(r"^((?:n\* by )?Nutrilite(?:™)?(?: Organics| Begin™)?|XS™|Artistry[^ ]*)\s+(.*)$", name)
    return (m.group(1), m.group(2)) if m else ("", name)


def main():
    d = sitedata.load()
    items = scaffold.product_index(d)
    kinds = scaffold.image_kinds()

    rows, seen = [], set()
    for n, line in enumerate((ROOT / "rooms.tsv").read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip() or line.startswith("#"):
            continue
        room, group, pid = [c.strip() for c in line.split("\t")]
        if room not in {r[0] for r in ROOMS}:
            sys.exit("rooms.tsv line %d: unknown room %r" % (n, room))
        if pid not in items:
            sys.exit("rooms.tsv line %d: %s is not in the data layer" % (n, pid))
        if pid in seen:
            sys.exit("rooms.tsv line %d: %s is placed twice" % (n, pid))
        seen.add(pid); rows.append((room, group, pid))
    unplaced = sorted(set(items) - seen)
    if unplaced:
        print("not in any room (add to rooms.tsv): " + ", ".join(unplaced))

    products = {}
    for pid, it in items.items():
        kind, img = kinds[pid]
        if kind == "cut" and not img.startswith("http"):
            img = "../" + img                        # the page lives in proto/
        fmt = next(f for f, rx in FORMAT_RULES if re.search(rx, it["name"]))
        brand, title = short(it["name"])
        products[pid] = {"n": title, "b": brand, "u": it["buy"], "i": img, "k": kind,
                         "f": fmt, "c": 0 if CAFFEINE_FREE.search(it["name"]) else 1}

    rooms = []
    for key, name, line in ROOMS:
        groups = []
        for room, group, pid in rows:
            if room != key:
                continue
            if not groups or groups[-1]["g"] != group:
                groups.append({"g": group, "ids": []})
            groups[-1]["ids"].append(pid)
        rooms.append({"key": key, "name": name, "line": line, "groups": groups,
                      "n": sum(len(g["ids"]) for g in groups)})

    for key, label, ids, why in GOALS:
        for pid in ids:
            if pid not in products:
                sys.exit("goal %s names %s, which is not in the data layer" % (key, pid))
    goals = [{"key": k, "label": l, "ids": ids, "why": w} for k, l, ids, w in GOALS]
    room_of = {pid: room for room, _, pid in rows}

    data = "/*DATA*/\n  var DATA = %s;\n  /*END DATA*/" % json.dumps(
        {"products": products, "rooms": rooms, "goals": goals, "roomOf": room_of},
        ensure_ascii=False, separators=(",", ":"))
    page = PAGE.read_text(encoding="utf-8")
    new, count = re.subn(r"/\*DATA\*/.*?/\*END DATA\*/", lambda m: data, page, flags=re.S)
    if count != 1:
        sys.exit("proto/pour.html needs exactly one /*DATA*/ ... /*END DATA*/ block")
    PAGE.write_text(new, encoding="utf-8")
    print("pour.html  %d products · %d rooms · %d goals · data %.1f KB"
          % (len(products), len(rooms), len(goals), len(data) / 1024))


if __name__ == "__main__":
    main()
