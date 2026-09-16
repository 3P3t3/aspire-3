#!/usr/bin/env python3
"""
sitedata.py — read-only loader for everything the site's DATA layer holds.

WHY THIS EXISTS
  rooms.html is a design. catalog.json, shelves.tsv, lead-images.tsv,
  hover-images.tsv and assets/rooms/ are the data — 52 share-links, the
  product photo Peter picked for each item, and the six personal photographs
  he selected. That work is expensive and has nothing to do with any
  particular design.

  This module exposes that data so a SECOND template can use it without
  re-wiring a single product, and without touching build_rooms.py, which
  keeps generating the live walkthrough exactly as it does today.

  Nothing here writes. Nothing here imports build_rooms. The .tsv and .json
  files remain the single source of truth; this only reads them.

USE IT
  python3 sitedata.py            # human summary — run this to sanity-check
  python3 sitedata.py --json     # the whole bundle as JSON, for a build script

  # from a build script:
  import sitedata
  d = sitedata.load()
  d["products"]   d["by_group"]   d["by_id"]
  d["shelves"]    d["leads"]      d["hover"]    d["photos"]
"""

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
CATALOG = HERE / "catalog.json"
HOVER_TSV = HERE / "hover-images.tsv"
SHELVES_TSV = HERE / "shelves.tsv"
LEADS_TSV = HERE / "lead-images.tsv"
PHOTOS_DIR = HERE / "assets" / "rooms"

MEDIA = "https://www.amway.com/medias/%s-en-US-%s?context=%s"

# Mirrors build_rooms.py. Kept here so a new template does not have to import
# the old build script; if these ever change there, change them here too.
GROUPS = [
    ("energy",    "Energy Drinks",       "XS energy, every flavour"),
    ("protein",   "Protein & Shakes",    "Whey, shakes and blends"),
    ("strength",  "Creatine & Strength", "Creatine, pre-workout, HMB"),
    ("bars",      "Bars & Snacks",       "Bars, crisps and twists"),
    ("hydration", "Hydration & Recovery","CocoWater & recovery"),
    ("focus",     "Energy + Focus",      "Focus support"),
]

SHELF_META = [
    ("sleep",         "My Sleep Stack",   "Maximize your body's natural recovery"),
    ("morning",       "My Morning Stack", "What goes in before anything else does"),
    ("treats",        "Protein Treats",   "Whey, and something to chew"),
    ("sportsnut",     "Sports Nutrition", "Focus, pre, post, and the recovery in between"),
    ("fridge",        "Optimal Energy",   "Every XS flavour, cold"),
    ("mirror",        "Skin Health",      "Cleanser, toner, and overnight repair"),
    ("glowup",        "Glow Up",          "Where the routine starts"),
    ("skinnutrition", "Skin Nutrition",   "What goes on after"),
]

HERO_ID = {
    "energy": "101444", "protein": "128154", "strength": "128463",
    "bars": "110385", "hydration": "110601", "focus": "101593",
}

# Personal photographs, by role. Files prefixed "_src-" are the originals
# Peter worked from and are deliberately excluded — only the selections.
PHOTO_ROLES = {
    "life-family.jpg":           "family at home",
    "life-beach.jpg":            "family at the beach",
    "life-portrait.jpg":         "portrait",
    "transformation-front.jpg":  "transformation, front",
    "transformation-side.jpg":   "transformation, side",
    "transformation-back.jpg":   "transformation, back",
}


def _rows(path, want_cols=None):
    if not path.exists():
        return
    for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        col = line.split("\t")
        if want_cols is not None and len(col) != want_cols:
            continue
        yield n, col


def load():
    if not CATALOG.exists():
        sys.exit("catalog.json not found next to sitedata.py")

    catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
    products = [p for bucket in catalog.values() for p in bucket]
    by_id = {p["id"]: p for p in products}

    by_group = {}
    for p in products:
        by_group.setdefault(p["group"], []).append(p)

    hover = {}
    for _, (pid, variant, token) in _rows(HOVER_TSV, 3):
        hover[pid] = MEDIA % (pid, variant, token)

    leads = {}
    for n, col in _rows(LEADS_TSV):
        if len(col) < 2:
            sys.exit("lead-images.tsv line %d has no lead value" % n)
        pid, want = col[0].strip(), col[1].strip()
        if want != "catalog" and not want.startswith("https://www.amway.com/medias/"):
            sys.exit("lead-images.tsv line %d: lead must be 'catalog' or an "
                     "Amway image URL, got %r" % (n, want))
        leads[pid] = want

    # Same three reference forms build_rooms.py resolves, so a shelf means
    # exactly what it means in the walkthrough.
    shelves = {}
    for n, col in _rows(SHELVES_TSV, 6):
        key, pid, short, full, url, token = col
        bucket = shelves.setdefault(key, [])
        if pid.startswith("@group:"):
            group = pid.split(":", 1)[1]
            if group not in by_group:
                sys.exit("shelves.tsv line %d: unknown group %r" % (n, group))
            for p in by_group[group]:
                bucket.append({"id": p["id"], "name": p["name"], "short": p["name"],
                               "buy": p["buy"], "img": p["img"],
                               "hover": hover.get(p["id"], "")})
        elif url == "@catalog":
            p = by_id.get(pid)
            if p is None:
                sys.exit("shelves.tsv line %d: %s is not in catalog.json" % (n, pid))
            bucket.append({"id": p["id"], "name": p["name"], "short": short or p["name"],
                           "buy": p["buy"], "img": p["img"],
                           "hover": hover.get(p["id"], "")})
        else:
            bucket.append({"id": pid, "name": full, "short": short, "buy": url,
                           "img": MEDIA % (pid, "690px-01", token),
                           "hover": hover.get(pid, "")})

    photos = []
    if PHOTOS_DIR.exists():
        for f in sorted(PHOTOS_DIR.glob("*")):
            if f.name.startswith("_src-") or f.suffix.lower() not in {".jpg", ".jpeg", ".png"}:
                continue
            photos.append({"file": f.name, "path": "assets/rooms/%s" % f.name,
                           "role": PHOTO_ROLES.get(f.name, ""),
                           "bytes": f.stat().st_size})

    heroes = {}
    for group, label, sub in GROUPS:
        h = by_id.get(HERO_ID.get(group, ""))
        if h:
            heroes[group] = {"id": h["id"], "name": h["name"], "img": h["img"],
                             "label": label, "sub": sub, "count": len(by_group.get(group, []))}

    return {
        "products": products, "by_id": by_id, "by_group": by_group,
        "shelves": shelves, "leads": leads, "hover": hover,
        "photos": photos, "heroes": heroes,
        "groups": GROUPS, "shelf_meta": SHELF_META,
    }


def main():
    d = load()
    if "--json" in sys.argv:
        print(json.dumps(d, ensure_ascii=False, indent=2))
        return
    print("Site data — read-only, shared by every template")
    print()
    print("  products        %d across %d groups" % (len(d["products"]), len(d["by_group"])))
    for g, label, _ in GROUPS:
        print("      %-10s %2d   hero: %s" % (
            g, len(d["by_group"].get(g, [])),
            d["heroes"].get(g, {}).get("name", "-")[:46]))
    print()
    print("  shelves         %d, %d items total" % (
        len(d["shelves"]), sum(len(v) for v in d["shelves"].values())))
    for key, title, _ in SHELF_META:
        print("      %-14s %2d  %s" % (key, len(d["shelves"].get(key, [])), title))
    print()
    print("  lead images     %d pinned (%d to the catalogue photo)" % (
        len(d["leads"]), sum(1 for v in d["leads"].values() if v == "catalog")))
    print("  hover images    %d" % len(d["hover"]))
    print()
    print("  photographs     %d selected" % len(d["photos"]))
    for p in d["photos"]:
        print("      %-26s %-24s %6.0f KB" % (p["file"], p["role"], p["bytes"] / 1024))
    print()
    print("  Every one of these is addressable from a new template with no rewiring.")


if __name__ == "__main__":
    main()
