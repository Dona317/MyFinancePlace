"""Shared by the live scripts: where the app runs, the checks and their summary, local copies of the CDN assets."""

import os
import subprocess
import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SAMPLES = ROOT / "samples" / "bank_statements"
BASE = os.environ.get("LIVE_URL", "http://localhost:5000")
DB = os.environ.get("LIVE_DATABASE_URL", "postgresql://sa:Pa55w0rd@localhost:5432/mfp_live")
OUT = Path(os.environ.get("LIVE_OUT", Path(__file__).resolve().parent / "out"))  # session, files, screenshots
AUTH = str(OUT / "auth.json")  # the logged-in session saved by login.py, reused by the other scripts
SHOTS = os.environ.get("LIVE_SHOTS")  # a folder: screenshot of every crawled page (to compare two runs)
ASSETS = os.environ.get("LIVE_ASSETS")  # a folder with chart.umd.js and bootstrap-icons/, when the CDNs are blocked
CHROMIUM = os.environ.get("LIVE_CHROMIUM") or None
OUT.mkdir(parents=True, exist_ok=True)
if SHOTS:
    Path(SHOTS).mkdir(parents=True, exist_ok=True)
results = []


def sql(query):
    return subprocess.run(["psql", "-tA", DB, "-c", query], capture_output=True, text=True).stdout.strip()


def check(name, ok, detail=""):
    results.append((bool(ok), name, detail))
    print(("  OK   " if ok else "  FAIL ") + name + (f"  [{detail}]" if detail and not ok else ""), flush=True)


def run(title, fn):
    """One block of checks; an exception fails the block and the run goes on."""
    print(f"\n== {title}", flush=True)
    try:
        fn()
    except Exception as exc:
        check(f"{title}: no exception", False, f"{type(exc).__name__}: {exc}".splitlines()[0][:200])
        traceback.print_exc(limit=2)


def summary(label):
    """Prints the result and returns the exit code (1 if any check failed)."""
    passed = sum(ok for ok, *_ in results)
    print(f"\n{label}: {passed}/{len(results)} checks passed")
    for ok, name, detail in results:
        if not ok:
            print("FAILED:", name, detail)
    return 0 if passed == len(results) else 1


def launch(playwright):
    return playwright.chromium.launch(executable_path=CHROMIUM)


def local_assets(page):
    """Serve Chart.js and Bootstrap Icons from LIVE_ASSETS instead of the CDNs (no-op when it is not set)."""
    if not ASSETS:
        return
    icons = Path(ASSETS) / "bootstrap-icons"
    page.route(
        "**/chart.umd.min.js", lambda r: r.fulfill(path=f"{ASSETS}/chart.umd.js", content_type="application/javascript")
    )
    page.route(
        "**/bootstrap-icons.min.css",
        lambda r: r.fulfill(path=icons / "bootstrap-icons.min.css", content_type="text/css"),
    )
    page.route(
        "**/fonts/bootstrap-icons.woff2*",
        lambda r: r.fulfill(path=icons / "fonts/bootstrap-icons.woff2", content_type="font/woff2"),
    )
    page.route(
        "**/fonts/bootstrap-icons.woff?*",
        lambda r: r.fulfill(path=icons / "fonts/bootstrap-icons.woff", content_type="font/woff"),
    )


if __name__ == "__main__":
    sys.exit("Run scripts/live/run.sh, or one of the scripts next to this file.")
