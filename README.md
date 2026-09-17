# One day, bed to bed

One day in one house as a single scroll-driven page, through six places:
nightstand, kitchen counter, by the door, desk, bathroom counter, and the
nightstand again. Each place owns a stretch of scroll travel, and that travel
scrubs its own clip — scroll down and it plays, scroll up and it reverses,
stop and it holds.

Each place has one container — a drawer, a bag, a counter — and the container
is the clickable. What's inside it is data, so adding a product never means new
footage.

**Motion here is placeholder.** Every place draws its own frame number and the
colour of its hour onto a canvas, so a scroll position can be read exactly.
The scroll feel is the thing being tested; footage comes after.

Phone first. 390px is the design; desktop is the adaptation. Footage is shot
9:16 and never cropped: on a phone it fills the screen, on desktop it becomes a
full-height column with the content beside it.

```bash
python3 tools/build_scaffold.py     # writes scaffold.html
python3 tools/serve.py 8777         # http://127.0.0.1:8777/scaffold.html
python3 tools/serve.py 8777 --lan   # also reachable from a phone
```

`scaffold.html` is self-contained apart from `assets/products/`. Open it
directly from disk and it works.

## Swapping in footage

Clip sources sit behind one interface — `frames`, `state`, `load()`,
`draw(ctx, i, w, h)` — with three implementations: placeholder, numbered frame
sequence, and short-GOP mp4. Every scene ships `media: null`. Giving a scene a
media block in `tools/build_scaffold.py` is the whole change:

```js
media: { kind: "frames", pattern: "scenes/03/%d.webp", frames: 56 }
media: { kind: "video",  src: "scenes/03.mp4", fps: 24, frames: 56 }
```

A source that is not ready returns `false` and the engine paints the flat
colour of the hour underneath, so first paint never waits on a clip.

## Loading

The first place is fetched eagerly after first paint. Every later one is pulled
by an IntersectionObserver as it is approached, never more than one ahead. Nothing
below the fold is fetched early.

## What's in each container

`stops.tsv` — one row per product: which container, an optional sub-heading,
and the product id. The build refuses to run if a product is in no container,
in two, or isn't in the data layer.

## The data layer

`catalog.json`, `shelves.tsv`, `lead-images.tsv` and `hover-images.tsv` hold 65
products with hand-minted share links. `sitedata.py` is a read-only loader over
all of it. The build reads products through it rather than restating them, so
every share link in the page is the one that was minted.

`image-kinds.tsv` records how each product image wants to be shown — `cut`
floats on the film, `photo` is framed as a photograph. Regenerate with:

```bash
python3 tools/classify_images.py    # decide the treatment per image
python3 tools/cutout_images.py      # remove the matte -> assets/products/
```

`cutout_images.py` flood-fills inward from the border, so only background
connected to the edge is removed and white inside a label survives. It needs
Pillow for WebP (`pip install --user pillow`) and falls back to PNG, which is
about six times larger. It skips work already done; `--all` redoes everything.

Product photography is Amway's, with the matte removed for demo use.

## Measured

At 390px, iPhone-class viewport:

| | |
|---|---|
| scrub frame | 0.15 ms mean, 0.3 ms p95 |
| scroll per frame | 20.3 px |
| first paint | 16 KB, type only |
| whole day | 1.2 MB, lazy per place |

Re-measure in the console with `DAY.bench(3)`. It is synchronous on purpose —
`requestAnimationFrame` is throttled in a background tab, which would measure
the browser rather than the page.

## Accessibility

Reduced motion gets one still per place, no scrubbing, every product still
reachable. Containers are real buttons and render open without JavaScript. Keyboard navigable end to end. Real alt text on all 65 images.
Touch targets 44px minimum.
