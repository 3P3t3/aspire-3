#!/usr/bin/env python3
"""
falgen.py - generate images/video through fal.ai and save them into this project.

WHY THIS EXISTS
  The Claude agent sandbox and the Claude desktop workspace are both blocked
  from reaching fal.ai (and every other generation API) by a network egress
  policy - a 403 at the CONNECT stage, before any key is sent. Your own macOS
  Terminal is NOT subject to that policy. So Claude writes the job file and
  this script; you run it. FAL_KEY is read from the environment.

RUN IT FROM YOUR OWN TERMINAL.app, NOT from Claude:
  cd ~/Desktop/aspiree
  python3 tools/falgen.py tools/jobs.json            # generate
  python3 tools/falgen.py tools/jobs.json --dry-run  # show plan + cost, call nothing
  python3 tools/falgen.py tools/jobs.json --force    # redo jobs already done
  python3 tools/falgen.py --check                    # key + network preflight only

Standard library only. No pip install. Nothing to set up.
The key is read from .env.agents and is never printed or written anywhere.
"""

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENV_FILE = os.path.join(ROOT, ".env.agents")
QUEUE = "https://queue.fal.run"
POLL_SECONDS = 3
POLL_TIMEOUT = 900  # 15 min ceiling per job; video can be slow


# ---------- small helpers ----------

class Bail(Exception):
    """Fatal, already-explained error."""


def load_key():
    if not os.path.exists(ENV_FILE):
        raise Bail(
            ".env.agents not found at %s\n"
            "It should hold a line like FAL_KEY=your-key-here" % ENV_FILE
        )
    for raw in open(ENV_FILE, encoding="utf-8"):
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, _, val = line.partition("=")
        if name.strip() == "FAL_KEY":
            val = val.strip().strip('"').strip("'")
            if not val:
                raise Bail("FAL_KEY in .env.agents is empty.")
            return val
    raise Bail("No FAL_KEY line found in .env.agents")


def post(url, key, payload):
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=body, method="POST")
    req.add_header("Authorization", "Key " + key)
    req.add_header("Content-Type", "application/json")
    return _send(req)


def get(url, key):
    req = urllib.request.Request(url, method="GET")
    req.add_header("Authorization", "Key " + key)
    return _send(req)


def _send(req):
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:600]
        if e.code in (401, 403):
            low = detail.lower()
            if "balance" in low or "locked" in low or "credit" in low or "quota" in low:
                raise Bail(
                    "Out of credit - this is a BILLING problem, not a key problem.\n"
                    "  fal says: %s\n"
                    "  Top up at https://fal.ai/dashboard/billing then re-run this\n"
                    "  exact command. Nothing was generated and nothing was charged."
                    % detail
                )
            raise Bail(
                "fal rejected the key (HTTP %d).\n"
                "  Check the key at https://fal.ai/dashboard/keys - it may have been\n"
                "  revoked or mistyped in .env.agents. Response: %s" % (e.code, detail)
            )
        if e.code == 404:
            raise Bail(
                "fal returned 404 - the model id in your job file is probably wrong.\n"
                "  Model ids change. Look up the exact one at https://fal.ai/models\n"
                "  (the id is the slug shown in the model's API example).\n"
                "  Response: %s" % detail
            )
        if e.code == 422:
            raise Bail(
                "fal rejected the inputs (422) - a field name or value is wrong for\n"
                "  this model. Each model has its own input schema; check the model's\n"
                "  page at https://fal.ai/models. Response: %s" % detail
            )
        raise Bail("fal returned HTTP %d: %s" % (e.code, detail))
    except urllib.error.URLError as e:
        raise Bail(
            "Could not reach fal.ai: %s\n"
            "  If this says 403 or 'policy', you are running inside the Claude\n"
            "  workspace rather than your own Terminal.app. Open Terminal on your\n"
            "  Mac, cd ~/Desktop/aspiree, and run it there." % e.reason
        )


def download(url, dest):
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    tmp = dest + ".part"
    with urllib.request.urlopen(url, timeout=300) as r, open(tmp, "wb") as f:
        while True:
            chunk = r.read(65536)
            if not chunk:
                break
            f.write(chunk)
    os.replace(tmp, dest)
    return os.path.getsize(dest)


def find_asset_urls(obj):
    """Walk a fal response and pull out every url that looks like an output file."""
    found = []

    def walk(node):
        if isinstance(node, dict):
            u = node.get("url")
            if isinstance(u, str) and u.startswith("http"):
                found.append(u)
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    walk(obj)
    seen, out = set(), []
    for u in found:
        if u not in seen:
            seen.add(u)
            out.append(u)
    return out


def human(n):
    for unit in ("B", "KB", "MB"):
        if n < 1024 or unit == "MB":
            return "%.0f%s" % (n, unit) if unit == "B" else "%.1f%s" % (n, unit)
        n /= 1024.0


# ---------- the work ----------

def resolve_local_files(inputs):
    """Turn "<name>_file": "path" into "<name>_url": data-URI, and
    "<name>_files": [paths] into "<name>_urls": [data-URIs].

    fal's image inputs accept data URIs, so a local keyframe can be sent inline
    without a separate upload step. Paths are relative to the project root.
    """
    import base64
    import mimetypes

    def uri(k, v):
        path = v if os.path.isabs(v) else os.path.join(ROOT, v)
        if not os.path.exists(path):
            raise Bail("input '%s' points at a missing file: %s" % (k, path))
        mime = mimetypes.guess_type(path)[0] or "image/jpeg"
        with open(path, "rb") as fh:
            return "data:%s;base64,%s" % (mime, base64.b64encode(fh.read()).decode("ascii"))

    out = {}
    for k, v in inputs.items():
        if k.endswith("_file") and isinstance(v, str):
            out[k[:-5] + "_url"] = uri(k, v)
        elif k.endswith("_files") and isinstance(v, list):
            # "image_files": [a, b] -> "image_urls": [data-URI, data-URI],
            # for models that take several reference images at once
            out[k[:-6] + "_urls"] = [uri(k, x) for x in v]
        else:
            out[k] = v
    return out


def run_job(job, key, out_root, force, dry):
    name = job.get("name") or "unnamed"
    model = job.get("model")
    inputs = job.get("input") or {}
    out_rel = job.get("out")
    note = job.get("cost_note", "")

    if not model or not out_rel:
        return ("skip", name, "job is missing 'model' or 'out'")

    dest = os.path.join(out_root, out_rel)
    if os.path.exists(dest) and not force:
        return ("have", name, "%s already exists (--force to redo)" % out_rel)

    if dry:
        return ("plan", name, "%s -> %s%s" % (model, out_rel, "  [%s]" % note if note else ""))

    inputs = resolve_local_files(inputs)
    payload_mb = len(json.dumps(inputs)) / 1048576.0
    if payload_mb > 1:
        print("    (payload %.1f MB)" % payload_mb)

    sub = post("%s/%s" % (QUEUE, model), key, inputs)
    status_url = sub.get("status_url")
    response_url = sub.get("response_url")
    if not status_url or not response_url:
        # Some endpoints answer synchronously with the result already attached.
        urls = find_asset_urls(sub)
        if not urls:
            return ("fail", name, "unexpected response, no status_url and no output url")
        size = download(urls[0], dest)
        return ("done", name, "%s (%s)" % (out_rel, human(size)))

    waited = 0
    while True:
        st = get(status_url, key)
        state = st.get("status")
        if state == "COMPLETED":
            break
        if state in ("FAILED", "ERROR", "CANCELLED"):
            return ("fail", name, "fal reported %s: %s" % (state, json.dumps(st)[:300]))
        if waited >= POLL_TIMEOUT:
            return ("fail", name, "timed out after %ds still %s" % (waited, state))
        qp = st.get("queue_position")
        sys.stdout.write("\r    %-28s %s%s   " % (
            name, state or "IN_QUEUE",
            "" if qp is None else " (queue pos %s)" % qp))
        sys.stdout.flush()
        time.sleep(POLL_SECONDS)
        waited += POLL_SECONDS

    sys.stdout.write("\r" + " " * 70 + "\r")
    result = get(response_url, key)
    urls = find_asset_urls(result)
    if not urls:
        return ("fail", name, "completed but no output url found: %s" % json.dumps(result)[:300])

    if len(urls) == 1:
        size = download(urls[0], dest)
        return ("done", name, "%s (%s)" % (out_rel, human(size)))

    base, ext = os.path.splitext(dest)
    total, written = 0, []
    for i, u in enumerate(urls, 1):
        d = "%s-%d%s" % (base, i, ext)
        total += download(u, d)
        written.append(os.path.relpath(d, out_root))
    return ("done", name, "%d files (%s): %s" % (len(written), human(total), ", ".join(written)))


def preflight(key):
    print("Preflight")
    print("  key            loaded from .env.agents (%d chars, not shown)" % len(key))
    try:
        urllib.request.urlopen(
            urllib.request.Request("https://fal.ai", method="HEAD"), timeout=15)
        print("  fal.ai         reachable")
    except urllib.error.HTTPError:
        print("  fal.ai         reachable")
    except urllib.error.URLError as e:
        print("  fal.ai         NOT reachable - %s" % e.reason)
        print()
        print("  If you are in your own Terminal.app and still see this, it is your")
        print("  network. If you ran this through Claude, that is expected: the")
        print("  Claude environments are blocked from fal by policy. Run it yourself:")
        print("      cd ~/Desktop/aspiree && python3 tools/falgen.py tools/jobs.json")
        return False
    return True


def main():
    ap = argparse.ArgumentParser(description="Generate fal.ai assets into this project.")
    ap.add_argument("jobs", nargs="?", help="path to a jobs JSON file")
    ap.add_argument("--out", default=os.path.join(ROOT, "assets", "generated"),
                    help="output root (default assets/generated)")
    ap.add_argument("--force", action="store_true", help="regenerate even if the file exists")
    ap.add_argument("--dry-run", action="store_true", help="print the plan, call nothing")
    ap.add_argument("--check", action="store_true", help="preflight only, then exit")
    args = ap.parse_args()

    try:
        key = load_key()
    except Bail as e:
        print("STOPPED: %s" % e)
        return 2

    if args.check:
        return 0 if preflight(key) else 1

    if not args.jobs:
        ap.error("need a jobs file (or use --check)")

    if not os.path.exists(args.jobs):
        print("STOPPED: jobs file not found: %s" % args.jobs)
        return 2
    try:
        spec = json.load(open(args.jobs, encoding="utf-8"))
    except json.JSONDecodeError as e:
        print("STOPPED: %s is not valid JSON - %s" % (args.jobs, e))
        return 2

    jobs = spec.get("jobs") if isinstance(spec, dict) else spec
    if not isinstance(jobs, list) or not jobs:
        print("STOPPED: no 'jobs' list in %s" % args.jobs)
        return 2

    if not args.dry_run and not preflight(key):
        return 1
    print()
    print("%d job(s) from %s" % (len(jobs), os.path.relpath(args.jobs, ROOT)))
    print("output root: %s" % os.path.relpath(args.out, ROOT))
    print()

    tally = {}
    for job in jobs:
        try:
            state, name, msg = run_job(job, key, args.out, args.force, args.dry_run)
        except Bail as e:
            state, name, msg = "fail", job.get("name", "unnamed"), str(e)
        tally[state] = tally.get(state, 0) + 1
        mark = {"done": "ok  ", "have": "have", "plan": "plan",
                "skip": "skip", "fail": "FAIL"}.get(state, "?   ")
        print("  %s %-28s %s" % (mark, name, msg))

    print()
    print("  ".join("%s=%d" % (k, v) for k, v in sorted(tally.items())))
    if tally.get("fail"):
        print()
        print("Some jobs failed. Nothing partial was left behind - failed jobs write")
        print("no file, so re-running picks up only what is missing.")
        return 1
    if args.dry_run:
        print()
        print("Dry run only. Nothing was generated and nothing was billed.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\ninterrupted")
        sys.exit(130)
