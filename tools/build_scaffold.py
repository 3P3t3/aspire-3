#!/usr/bin/env python3
"""
build_scaffold.py — emits scaffold.html: the day, as one self-contained file.

Products are read from the DATA layer through sitedata.py, never retyped, so
every share-link in the built page is the one that was minted by hand.

  python3 tools/build_scaffold.py
"""

import html
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))
import sitedata  # noqa: E402

OUT = ROOT / "scaffold.html"

# ---------------------------------------------------------------- the day
# Six stops, bed to bed. Each is a PLACE with a CONTAINER in it. The footage
# shows the place; the container is the clickable; what is inside it is data
# (containers.tsv, contents.tsv). Adding a product never means new footage.
#
# frames: about 2-3 seconds at 24fps per stop; the kitchen holds four
# containers and gets ~6 seconds (144) for one slow move across them.
#
# t0/t1 are minutes past midnight; c0/c1 the light at each end. Each stop ends
# on the colour the next one starts on, so the day runs continuously — the same
# chain the footage uses. Stops 1 and 6 are the same room: the light is what
# has to tell a fast scroller that a day has passed.
STOPS = [
    dict(n=1, key="nightstand-am", title="Nightstand",
         frames=60, t0=370, t1=395, c0="#1d2233", c1="#7a6a5c",
         head=("Before the house", " is awake"),
         line="Feet on the floor. The drawer, first.",
         alt="Morning. Low sun through the bedroom window; a hand opens the "
             "nightstand drawer beside a slept-in bed."),
    dict(n=2, key="kitchen", title="Kitchen counter",
         frames=144, t0=460, t1=490, c0="#7a6a5c", c1="#cdb797",
         head=("A scoop,", " not a recipe"),
         line="The sun is up properly now. Blender, shaker, done.",
         alt="Kitchen counter in hard mid-morning light; hands scoop protein "
             "into a blender. A second mug sits in the sink."),
    dict(n=3, key="bag", title="By the door",
         frames=48, t0=490, t1=505, c0="#cdb797", c1="#a8a39a",
         head=("Packed", " on the way out"),
         line="Open on the bench. Something for training, something for later.",
         alt="By the front door in flat hallway light; a training bag open on a "
             "bench, being packed, with a smaller bag beside it."),
    dict(n=4, key="desk", title="Desk",
         frames=72, t0=900, t1=940, c0="#a8a39a", c1="#8f8a80",
         head=("The slump", " is the reason"),
         line="Mid-afternoon, the flattest light of the day. The can gets opened here.",
         alt="A plain desk in flat, tired afternoon light; a hand cracks open a "
             "can of XS."),
    dict(n=5, key="bathroom", title="Bathroom counter",
         frames=56, t0=1300, t1=1325, c0="#8f8a80", c1="#3a3530",
         head=("The end of the day", " starts here"),
         line="Dark outside. The light over the mirror does all the work.",
         alt="Bathroom counter at night under the mirror light; hands at the "
             "sink, a little steam, the window black."),
    dict(n=6, key="nightstand-pm", title="Nightstand",
         frames=66, t0=1325, t1=1360, c0="#3a3530", c1="#120f0d",
         head=("Same drawer,", " different things in it"),
         line="The window is black. The lamp is the only light left.",
         alt="The same bedroom at night, lit only by the nightstand lamp; the "
             "drawer opens again."),
]


# ------------------------------------------------------------ after the day
# The closing section: no footage, no products. Launches in November.
# PLACEHOLDER COPY — replace with the program's approved wording and whatever
# disclosures it requires before this goes live.
OVERNIGHT = dict(
    eyebrow="Overnight",
    when="Launching November",
    head=("After the house", " is asleep"),
    line="Everything above is the part of the day you can see. This is the part "
         "you can't: what your body is actually short on, measured instead of "
         "guessed.",
    steps=[
        ("Bloodwork, from home", "A kit comes to you. No clinic, no waiting room."),
        ("A doctor reads it", "A licensed physician goes through your labs with you."),
        ("A plan, if you need one",
         "Where it's right for you, that can include peptide therapy — prescribed "
         "by the doctor and filled by a licensed compounding pharmacy."),
    ],
)

def _tsv(name, cols):
    path = ROOT / name
    if not path.exists():
        sys.exit("%s missing" % name)
    for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip() or line.startswith("#"):
            continue
        col = [c.strip() for c in line.split("\t")]
        if len(col) != cols:
            sys.exit("%s line %d: expected %d tab-separated columns" % (name, n, cols))
        yield n, col


def load_boxes():
    """containers.tsv + contents.tsv -> each stop's containers, in order.

    A stop can hold any number of containers. Each container holds groups of
    product ids. A container with nothing in it yet is kept (it's still a
    footage requirement) but the page doesn't show it."""
    stops = {st["key"] for st in STOPS}
    boxes, by_key = {st["key"]: [] for st in STOPS}, {}
    for n, (key, stop, label, where) in _tsv("containers.tsv", 4):
        if stop not in stops:
            sys.exit("containers.tsv line %d: unknown stop %r" % (n, stop))
        if key in by_key:
            sys.exit("containers.tsv line %d: container %r defined twice" % (n, key))
        box = dict(key=key, label=label, where=where, clusters=[])
        boxes[stop].append(box)
        by_key[key] = box
    for n, (key, group, pid) in _tsv("contents.tsv", 3):
        if key not in by_key:
            sys.exit("contents.tsv line %d: unknown container %r" % (n, key))
        g = by_key[key]["clusters"]
        if not g or g[-1][0] != group:
            g.append((group, []))
        g[-1][1].append(pid)
    return boxes


# The stops with their containers attached. `clusters` flattens every
# container's groups — other tools (classify, cutout) import SCENES for that.
_BOXES = load_boxes()
SCENES = [dict(st, boxes=_BOXES[st["key"]],
               clusters=[c for bx in _BOXES[st["key"]] for c in bx["clusters"]])
          for st in STOPS]


def product_index(d):
    """Every product the data layer knows, catalog plus shelf-only rows."""
    items = {}
    for p in d["products"]:
        items[p["id"]] = {"id": p["id"], "name": p["name"], "buy": p["buy"], "img": p["img"]}
    for rows in d["shelves"].values():
        for it in rows:
            items.setdefault(it["id"], {"id": it["id"], "name": it["name"],
                                        "buy": it["buy"], "img": it["img"]})
    # lead-images.tsv pins a hand-picked photograph for 41 of them.
    for pid, lead in d["leads"].items():
        if pid in items and lead != "catalog":
            items[pid]["img"] = lead
    return items


def image_kinds():
    """'cut' floats on the film, 'photo' is framed as a photograph.

    A matte removed by tools/cutout_images.py wins: that file is the same
    packshot with the white knocked out, so it floats like the rest. What is
    left as 'photo' is genuinely a photograph — a product on rocks, on moss,
    in a hand — and those are meant to be framed."""
    path = ROOT / "image-kinds.tsv"
    if not path.exists():
        sys.exit("image-kinds.tsv missing — run: python3 tools/classify_images.py")
    out = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip() and not line.startswith("#"):
            pid, k, url = line.split("\t")
            for ext in ("webp", "png"):
                cut = ROOT / "assets" / "products" / ("%s.%s" % (pid, ext))
                if cut.exists():
                    out[pid] = ("cut", "assets/products/%s.%s" % (pid, ext))
                    break
            else:
                out[pid] = (k.strip(), url.strip())
    return out


def card(it, kind, img):
    name = html.escape(it["name"])
    return (
        '<li><a class="card %s" href="%s" target="_blank" rel="noopener">'
        '<span class="shot"><img src="%s" alt="%s" loading="lazy" decoding="async" '
        'width="690" height="690"></span>'
        '<span class="name">%s</span><span class="go">Shop</span></a></li>'
        % (kind, html.escape(it["buy"]), html.escape(img), name, name)
    )


def build():
    d = sitedata.load()
    items = product_index(d)

    placed_list = [pid for sc in SCENES for _, ids in sc["clusters"] for pid in ids]
    missing = [pid for pid in placed_list if pid not in items]
    if missing:
        sys.exit("contents.tsv names products not in the data layer: %s" % ", ".join(missing))
    dupes = sorted({pid for pid in placed_list if placed_list.count(pid) > 1})
    if dupes:
        sys.exit("contents.tsv places a product twice: %s" % ", ".join(dupes))
    orphan = sorted(set(items) - set(placed_list))
    if orphan:
        sys.exit("product(s) in no container — add a row to contents.tsv: %s" %
                 ", ".join("%s %s" % (p, items[p]["name"]) for p in orphan))

    kinds = image_kinds()
    css = (HERE / "scaffold" / "day.css").read_text(encoding="utf-8")
    js = (HERE / "scaffold" / "day.js").read_text(encoding="utf-8")

    sections, index, sheet = [], [], []
    empty = []
    for sc in SCENES:
        rendered, labels = [], []
        for bx in sc["boxes"]:
            count = sum(len(ids) for _, ids in bx["clusters"])
            if not count:
                empty.append("%s / %s" % (sc["title"], bx["label"]))
                continue
            body = []
            for label, ids in bx["clusters"]:
                cards = "".join(
                    card(items[p], *kinds.get(p, ("photo", items[p]["img"]))) for p in ids)
                head = ('<h3>%s<s></s></h3>' % html.escape(label)) if label else ""
                body.append('<div class="cluster">%s<ul class="grid">%s</ul></div>'
                            % (head, cards))
            # The container is the clickable. Rendered OPEN, so every product is
            # reachable with no JavaScript; the engine closes them on load.
            rendered.append(
                '<div class="box">\n'
                '      <button class="box-btn" type="button" aria-expanded="true" '
                'aria-controls="box-%s"><span class="box-name">%s</span>'
                '<span class="box-count">%d</span></button>\n'
                '      <div class="box-body" id="box-%s">\n        %s\n      </div>\n'
                '    </div>'
                % (bx["key"], html.escape(bx["label"]), count, bx["key"],
                   "\n        ".join(body)))
            labels.append("%s %d" % (bx["label"], count))
        sections.append(
            '<section class="scene" id="scene-%d" data-scene="%d" '
            'style="--frames:%d;--c0:%s;--c1:%s" aria-labelledby="h-%d">\n'
            '  <div class="stage"><canvas role="img" aria-label="%s"></canvas></div>\n'
            '  <div class="flow">\n'
            '    <div class="beat">\n'
            '      <p class="eyebrow"><b>%02d</b> <u>%s</u><s></s>'
            '<i>%s<span>–%s</span></i></p>\n'
            '      <h2 id="h-%d">%s<em>%s</em></h2>\n'
            '      <p>%s</p>\n'
            '    </div>\n'
            '    %s\n'
            '  </div>\n'
            '</section>'
            % (sc["n"], sc["n"], sc["frames"], sc["c0"], sc["c1"], sc["n"],
               html.escape(sc["alt"]), sc["n"], html.escape(sc["title"]),
               _clock(sc["t0"]), _clock(sc["t1"]), sc["n"],
               html.escape(sc["head"][0]), html.escape(sc["head"][1]),
               html.escape(sc["line"]), "\n    ".join(rendered))
        )
        sheet.append('<a href="#scene-%d"><b>%s</b><span>%s</span></a>'
                     % (sc["n"], _clock(sc["t0"]), html.escape(sc["title"])))
        index.append('<li><a href="#scene-%d"><b>%s</b><span>%s</span></a></li>'
                     % (sc["n"], _clock(sc["t0"]),
                        html.escape("%s — %s" % (sc["title"], ", ".join(labels)))))

    data = [{k: sc[k] for k in ("n", "key", "title", "frames", "t0", "t1", "c0", "c1")}
            for sc in SCENES]
    for row in data:
        row["media"] = None          # ← swap in footage here, nothing else changes

    total = len(placed_list)
    ov = OVERNIGHT
    overnight = (
        '<section class="overnight" id="overnight" aria-labelledby="h-overnight">\n'
        '    <p class="eyebrow"><u>%s</u><s></s><i>%s</i></p>\n'
        '    <h2 id="h-overnight">%s<em>%s</em></h2>\n'
        '    <p class="ov-line">%s</p>\n'
        '    <ol class="steps">%s</ol>\n'
        '  </section>'
        % (html.escape(ov["eyebrow"]), html.escape(ov["when"]),
           html.escape(ov["head"][0]), html.escape(ov["head"][1]),
           html.escape(ov["line"]),
           "".join('<li><b>%02d</b><h3>%s</h3><p>%s</p></li>'
                   % (i + 1, html.escape(t), html.escape(d))
                   for i, (t, d) in enumerate(ov["steps"]))))
    sheet.append('<a href="#overnight"><b>Night</b><span>%s</span></a>'
                 % html.escape(ov["eyebrow"]))
    index.append('<li><a href="#overnight"><b>Night</b><span>%s</span></a></li>'
                 % html.escape("%s — %s" % (ov["eyebrow"], ov["when"].lower())))
    page = TEMPLATE.replace("/*CSS*/", css) \
                   .replace("/*JS*/", js) \
                   .replace("/*SCENES*/", json.dumps(data, separators=(",", ":"))) \
                   .replace("<!--SECTIONS-->", "\n".join(sections)) \
                   .replace("<!--SHEET-->", "".join(sheet)) \
                   .replace("<!--INDEX-->", "".join(index)) \
                   .replace("<!--OVERNIGHT-->", overnight) \
                   .replace("<!--COUNT-->", str(total))
    OUT.write_text(page, encoding="utf-8")
    shown = sum(1 for sc in SCENES for bx in sc["boxes"]
                if any(ids for _, ids in bx["clusters"]))
    print("scaffold.html  %.1f KB  ·  %d stops  ·  %d containers shown  ·  %d products"
          % (OUT.stat().st_size / 1024, len(SCENES), shown, total))
    if empty:
        print("containers waiting for products (not shown): " + "; ".join(empty))


def _clock(m):
    return "%02d:%02d" % (m // 60 % 24, m % 60)


TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<script>document.documentElement.classList.add("js")</script>
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>A day — placeholder motion</title>
<meta name="description" content="One day in one house, bed to bed. Scrolling moves time forward through six places.">
<meta name="theme-color" content="#12141f">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="preconnect" href="https://www.amway.com">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Fraunces:ital,opsz,wght@0,9..144,300..600;1,9..144,300..500&family=Inter:wght@400;500;600&display=swap">
<style>/*CSS*/</style>
</head>
<body>
<a class="skip" href="#scene-1">Skip to the day</a>

<header class="bar">
  <span class="clock" id="clock" aria-live="off">06:10</span>
  <span class="bar-beat" id="barbeat">Nightstand</span>
  <span class="hud" id="hud" aria-hidden="true">S1 000/59</span>
  <button class="bar-btn" id="beatsbtn" aria-expanded="false" aria-controls="sheet">Day</button>
</header>
<div class="daybar" aria-hidden="true"><i id="daybar"></i></div>

<nav class="sheet" id="sheet" aria-label="The day, by place">
  <button class="sheet-close" id="sheetclose">Close</button>
  <h2>The day</h2>
  <!--SHEET-->
</nav>

<main>
  <section class="open">
    <h1>One day,<br>bed to <em>bed</em></h1>
    <div class="rule"></div>
    <p>Scrolling moves time forward. Six places in one house, from the first
       light to the lamp going off. Open what's in each one.</p>
    <p class="cue"><i></i> Scroll</p>
  </section>

<!--SECTIONS-->

  <!--OVERNIGHT-->

  <section class="end" id="end">
    <h2>That was the day.</h2>
    <p><!--COUNT--> products, each one kept where it's actually used.</p>
    <ol><!--INDEX--></ol>
    <p class="note">Motion is placeholder: every place draws its own frame
      number and the colour of its hour, so a scroll position can be read
      exactly. The first place loads eagerly; every later one is pulled in as it
      is approached. Product photography is Amway's.</p>
  </section>
</main>

<script>window.__SCENES__=/*SCENES*/;</script>
<script>/*JS*/</script>
</body>
</html>
"""

if __name__ == "__main__":
    build()
