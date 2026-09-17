#!/usr/bin/env python3
"""frames.py — turn generated clips into one numbered WebP frame sequence the
page can scrub (FrameSequenceSource).

    python3 tools/frames.py assets/generated/stop1/take-kling.mp4 kling
    python3 tools/frames.py clipA.mp4 clipB.mp4 stop1 --every 2
    python3 tools/frames.py clipA2.mp4:66 clipB.mp4 stop1 --every 2

A clip written as path:N is used from its frame N onward (1-based), to trim
off an opening that went wrong.

--inset F trims the fraction F from every edge of every frame (0.10 = a 1.25x
push-in), keeping the shape. Use it to lose something that crept in at the
edge of a take — applied to the whole stop, so joins between clips stay clean.

Several clips are joined in order, as one stop. Where clip B was generated
starting on clip A's last frame, that shared frame appears once, not twice.
--every N keeps every Nth frame: the motion stays smooth under a thumb and the
stop needs 1/N of the scroll.

Writes frames-<name>/0001.webp ... next to the first clip, scaled to 1440px
tall — enough for a phone's canvas, about 1690 device pixels tall at the 2x
cap the engine uses. Needs imageio-ffmpeg (pip install --user imageio-ffmpeg),
which bundles ffmpeg.
"""
import shutil, subprocess, sys, tempfile
from pathlib import Path

import imageio_ffmpeg

ROOT = Path(__file__).resolve().parent.parent
FF = imageio_ffmpeg.get_ffmpeg_exe()


def probe(path):
    r = subprocess.run([FF, "-hide_banner", "-i", str(path)], capture_output=True, text=True)
    return next((l.strip() for l in r.stderr.splitlines() if "Video:" in l), "")


def extract(clip, dest, inset=0.0):
    vf = "scale=-2:1440:flags=lanczos"
    if inset:
        keep = 1 - 2 * inset
        vf = "crop=iw*%.4f:ih*%.4f:iw*%.4f:ih*%.4f," % (keep, keep, inset, inset) + vf
    subprocess.run([FF, "-hide_banner", "-loglevel", "error", "-i", str(clip),
                    "-vf", vf, "-an",
                    "-c:v", "libwebp", "-quality", "82", "-compression_level", "4",
                    str(dest / "%05d.webp")], check=True)
    return sorted(dest.glob("*.webp"))


def main():
    args = sys.argv[1:]
    every = 1
    if "--every" in args:
        i = args.index("--every")
        every = int(args[i + 1])
        del args[i:i + 2]
    inset = 0.0
    if "--inset" in args:
        i = args.index("--inset")
        inset = float(args[i + 1])
        del args[i:i + 2]
    if len(args) < 2:
        sys.exit(__doc__)
    *specs, name = args
    clips, starts = [], []
    for c in specs:
        path, _, start = c.rpartition(":") if c.rpartition(":")[2].isdigit() else (c, "", "1")
        clips.append(Path(path).resolve())
        starts.append(int(start))
    out = clips[0].parent / ("frames-" + name)
    out.mkdir(exist_ok=True)
    for old in out.glob("*.webp"):
        old.unlink()

    seq, tmp = [], Path(tempfile.mkdtemp())
    try:
        for k, clip in enumerate(clips):
            d = tmp / str(k)
            d.mkdir()
            frames = extract(clip, d, inset)
            total = len(frames)
            frames = frames[starts[k] - 1:]
            if k and starts[k] == 1:                 # shared join frame: keep once
                frames = frames[1:]
            seq += frames
            print("%-14s %s  (using %d of %d frames%s)" % (
                clip.name, probe(clip)[:60], len(frames), total,
                ", from %d" % starts[k] if starts[k] > 1 else ""))
        kept = seq[::every]
        if seq and kept[-1] != seq[-1]:              # always end on the true last frame
            kept.append(seq[-1])
        for n, f in enumerate(kept, 1):
            shutil.copyfile(f, out / ("%04d.webp" % n))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    files = sorted(out.glob("*.webp"))
    size = sum(f.stat().st_size for f in files)
    print("  -> %d frames%s, %.1f MB, %s" % (
        len(files), " (every %d of %d)" % (every, len(seq)) if every > 1 else "",
        size / 1e6, out.relative_to(ROOT)))


if __name__ == "__main__":
    main()
