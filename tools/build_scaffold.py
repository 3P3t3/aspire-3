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
# Eight beats. t0/t1 are minutes past midnight; c0/c1 the light at each end.
# The end colour of a beat is the start colour of the next, so the day runs
# continuously across all eight — the same chain the footage will use.
SCENES = [
    dict(n=1, key="wake", title="Wake", frames=60, t0=348, t1=365,
         c0="#171c30", c1="#2a3147",
         head=("First light, and", " nothing has happened yet"),
         line="Feet on the floor. The room is still blue.",
         tail="Thirty seconds of sitting there before any of it starts.",
         alt="Bedroom before sunrise, sitting up on the edge of the bed.",
         clusters=[]),
    dict(n=2, key="gut", title="Gut, first thing", frames=48, t0=365, t1=390,
         c0="#2a3147", c1="#6a6274",
         head=("Before", " anything else"),
         line="Nothing has gone in today. This goes in first.",
         tail="It is not a ritual. It is just first.",
         alt="Still in the bedroom, a glass of water in hand before the day starts.",
         clusters=[("", ["127725", "120571"])]),
    dict(n=3, key="load", title="Twist and load", frames=56, t0=390, t1=430,
         c0="#6a6274", c1="#b09174",
         head=("Twist, and the", " water changes colour"),
         line="Bottle under the tap. A scoop, a tube, done standing up.",
         alt="Water running into a bottle on the counter, a scoop resting beside it.",
         clusters=[("The scoop", ["128463"]),
                   ("The twist", ["110922", "110390", "305555"]),
                   ("The water", ["110601", "110631"])]),
    dict(n=4, key="kitchen", title="Kitchen", frames=60, t0=430, t1=480,
         c0="#b09174", c1="#d8c6a8",
         head=("A scoop,", " not a recipe"),
         line="Chocolate. Shaker. Out the door holding it.",
         alt="Morning kitchen in motion, a shaker being filled on the way past.",
         clusters=[("Whey", ["128154", "128155", "128156"]),
                   ("Sachets, for the bag", ["128167", "128168", "128169"]),
                   ("Ready to go", ["110369", "110370"])]),
    dict(n=5, key="office", title="Office", frames=72, t0=480, t1=880,
         c0="#d8c6a8", c1="#cdc9bd",
         head=("The middle of the day", " passes here"),
         line="Three hours in, the screen stops being interesting.",
         tail="Two emails matter. The rest is weather.",
         alt="At a desk through the middle of the day, light flattening across the room.",
         clusters=[("", ["101593", "107846", "266673"])]),
    dict(n=6, key="hunger", title="Hunger", frames=48, t0=880, t1=940,
         c0="#cdc9bd", c1="#c9a97e",
         head=("The stomach", " turns over"),
         line="Not a meal. Something to chew, and back to it.",
         alt="Reaching into a drawer for a bar without looking up from the desk.",
         clusters=[("The reach", ["110385", "110386"]),
                   ("Also in the drawer", ["316302", "316303", "316305"]),
                   ("Salt, some days", ["110627", "110628"])]),
    dict(n=7, key="lift", title="Lift", frames=72, t0=940, t1=1110,
         c0="#c9a97e", c1="#8c5f45",
         head=("Cold can,", " then the bar"),
         line="The part of the day that belongs to nobody else.",
         alt="Late afternoon, a cold can lifted off the shelf on the way to train.",
         clusters=[("Before", ["316375", "316376", "316377", "316378", "127811"]),
                   ("The fridge", ["101444", "126184", "126197", "126198", "126199",
                                   "126201", "126202", "126883", "126981", "126982",
                                   "126983", "126984", "126986", "126987", "126998",
                                   "127070", "127071", "127935", "127936", "128583"]),
                   ("After", ["316379", "316380", "126753", "126754", "296753", "300323"])]),
    dict(n=8, key="night", title="Night", frames=66, t0=1110, t1=1360,
         c0="#8c5f45", c1="#12141f",
         head=("Wash the day off,", " then the lamp"),
         line="A small pile by the bed, and the light goes down.",
         alt="Bathroom mirror at night, then the nightstand under a low lamp.",
         clusters=[("The mirror", ["124812", "123783V", "125575"]),
                   ("The nightstand", ["128032", "308641", "124506", "127940", "308636"])]),
]


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

    missing = [pid for sc in SCENES for _, ids in sc["clusters"] for pid in ids if pid not in items]
    if missing:
        sys.exit("not in the data layer: %s" % ", ".join(missing))
    placed = {pid for sc in SCENES for _, ids in sc["clusters"] for pid in ids}
    orphan = sorted(set(items) - placed)
    if orphan:
        sys.exit("product(s) with no place in the day: %s" %
                 ", ".join("%s %s" % (p, items[p]["name"]) for p in orphan))

    kinds = image_kinds()
    css = (HERE / "scaffold" / "day.css").read_text(encoding="utf-8")
    js = (HERE / "scaffold" / "day.js").read_text(encoding="utf-8")

    sections, index, sheet = [], [], []
    for sc in SCENES:
        body = []
        for label, ids in sc["clusters"]:
            cards = "".join(
                card(items[p], *kinds.get(p, ("photo", items[p]["img"]))) for p in ids)
            head = ('<h3>%s<s></s></h3>' % html.escape(label)) if label else ""
            body.append('<div class="cluster">%s<ul class="grid">%s</ul></div>' % (head, cards))
        count = sum(len(ids) for _, ids in sc["clusters"])
        sections.append(
            '<section class="scene" id="scene-%d" data-scene="%d" '
            'style="--frames:%d;--c0:%s;--c1:%s" aria-labelledby="h-%d">\n'
            '  <div class="stage"><canvas role="img" aria-label="%s"></canvas></div>\n'
            '  <div class="flow">\n'
            '    <div class="beat">\n'
            '      <p class="eyebrow"><b>%02d</b> <u>%s</u><s></s>'
            '<i>%s<span>\u2013%s</span></i></p>\n'
            '      <h2 id="h-%d">%s<em>%s</em></h2>\n'
            '      <p>%s</p>\n'
            '    </div>\n'
            '    %s%s\n'
            '  </div>\n'
            '</section>'
            % (sc["n"], sc["n"], sc["frames"], sc["c0"], sc["c1"], sc["n"],
               html.escape(sc["alt"]), sc["n"], html.escape(sc["title"]),
               _clock(sc["t0"]), _clock(sc["t1"]), sc["n"],
               html.escape(sc["head"][0]), html.escape(sc["head"][1]),
               html.escape(sc["line"]), "\n    ".join(body),
               ('<p class="tail">%s</p>' % html.escape(sc["tail"])) if sc.get("tail") else "")
        )
        link = ('<a href="#scene-%d"><b>%s</b><span>%s</span></a>'
                % (sc["n"], _clock(sc["t0"]), html.escape(sc["title"])))
        sheet.append(link)
        index.append('<li><a href="#scene-%d"><b>%s</b><span>%s</span></a></li>'
                     % (sc["n"], _clock(sc["t0"]),
                        html.escape("%s — %s" % (sc["title"],
                            "before anything goes in" if not count
                            else "%d product%s" % (count, "" if count == 1 else "s")))))

    data = [{k: sc[k] for k in ("n", "key", "title", "frames", "t0", "t1", "c0", "c1")}
            for sc in SCENES]
    for row in data:
        row["media"] = None          # ← swap in footage here, nothing else changes

    total = sum(sum(len(i) for _, i in s["clusters"]) for s in SCENES)
    page = TEMPLATE.replace("/*CSS*/", css) \
                   .replace("/*JS*/", js) \
                   .replace("/*SCENES*/", json.dumps(data, separators=(",", ":"))) \
                   .replace("<!--SECTIONS-->", "\n".join(sections)) \
                   .replace("<!--SHEET-->", "".join(sheet)) \
                   .replace("<!--INDEX-->", "".join(index)) \
                   .replace("<!--COUNT-->", str(total))
    OUT.write_text(page, encoding="utf-8")
    print("scaffold.html  %.1f KB  ·  %d scenes  ·  %d products  ·  %d frames total"
          % (OUT.stat().st_size / 1024, len(SCENES), total,
             sum(s["frames"] for s in SCENES)))


def _clock(m):
    return "%02d:%02d" % (m // 60 % 24, m % 60)


TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>A day — placeholder motion</title>
<meta name="description" content="One person's day in eight beats. Scrolling moves time forward; each beat scrubs its own clip.">
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
  <span class="clock" id="clock" aria-live="off">05:48</span>
  <span class="bar-beat" id="barbeat">Wake</span>
  <span class="hud" id="hud" aria-hidden="true">S1 000/59</span>
  <button class="bar-btn" id="beatsbtn" aria-expanded="false" aria-controls="sheet">Beats</button>
</header>
<div class="daybar" aria-hidden="true"><i id="daybar"></i></div>

<nav class="sheet" id="sheet" aria-label="The eight beats">
  <button class="sheet-close" id="sheetclose">Close</button>
  <h2>The day</h2>
  <!--SHEET-->
</nav>

<main>
  <section class="open">
    <h1>One day,<br>eight <em>beats</em></h1>
    <div class="rule"></div>
    <p>Scrolling moves time forward. Each beat holds a stretch of the day and
       scrubs its own clip — down it plays, up it reverses, stop and it holds.</p>
    <p class="cue"><i></i> Scroll</p>
  </section>

<!--SECTIONS-->

  <section class="end" id="end">
    <h2>That was the day.</h2>
    <p><!--COUNT--> products, each one where it actually belongs.</p>
    <ol><!--INDEX--></ol>
    <p class="note">Motion is placeholder: every beat draws its own frame number
      and the colour of its hour, so a scroll position can be read exactly.
      Scene&nbsp;1 loads eagerly; every later beat is pulled in as it is
      approached. Product photography is Amway's, served from source.</p>
  </section>
</main>

<script>window.__SCENES__=/*SCENES*/;</script>
<script>/*JS*/</script>
</body>
</html>
"""

if __name__ == "__main__":
    build()
