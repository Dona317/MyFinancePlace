"""
The notice of a new version (F23), only in the desktop app: once a day one request to GitHub for the latest release,
when switched on in Settings → App desktop. Nothing is downloaded or installed by itself: the notice links to the
release page. The answer is kept in the data folder (update.json), shared by every archive.
"""
from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from datetime import date
from pathlib import Path

from app.version import __version__

LATEST_URL = "https://api.github.com/repos/Dona317/MyFinancePlace/releases/latest"
RELEASES_PAGE = "https://github.com/Dona317/MyFinancePlace/releases"
FILE = "update.json"
TIMEOUT = 8


def parse(version: str | None) -> tuple[int, ...]:
    """'v1.2.10' → (1, 2, 10); anything after the numbers (a «-beta») is ignored."""
    found = re.match(r"v?(\d+(?:\.\d+)*)", (version or "").strip())
    return tuple(int(part) for part in found.group(1).split(".")) if found else ()


def _fetch() -> dict | None:
    request = urllib.request.Request(LATEST_URL, headers={"Accept": "application/vnd.github+json",
                                                          "User-Agent": f"MyFinancePlace/{__version__}"})
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
            return json.loads(response.read())
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return {}  # no release published yet
        return None
    except (urllib.error.URLError, OSError, ValueError):
        return None


def stored(folder: Path) -> dict:
    try:
        found = json.loads((Path(folder) / FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return found if isinstance(found, dict) else {}


def check(folder: Path, today: date | None = None, fetch=None) -> dict:
    """The latest release, asked at most once a day; a failed request is tried again the next round."""
    today = today or date.today()
    known = stored(folder)
    if known.get("checked") == today.isoformat():
        return known
    answer = (fetch or _fetch)()
    if answer is None:
        return known
    known = {"checked": today.isoformat(), "version": str(answer.get("tag_name") or "").lstrip("v") or None,
             "url": answer.get("html_url") or RELEASES_PAGE}
    (Path(folder) / FILE).write_text(json.dumps(known), encoding="utf-8")
    return known


def newer(folder: Path) -> dict | None:
    """The release found, when it is newer than this app."""
    known = stored(folder)
    return known if known.get("version") and parse(known["version"]) > parse(__version__) else None
