"""
The Bootstrap Icons the app uses, served from app/static/vendor/icons (no CDN: the desktop app works offline).
Only the icons named somewhere in the app are kept: about 10 KB instead of 220 KB.

Run it again after using a new icon (needs fonttools and brotli, only on the machine that runs it):

    npm pack bootstrap-icons@1.11.3 && tar xf bootstrap-icons-1.11.3.tgz
    python scripts/icons.py package/font
"""
import json
import re
import sys
from pathlib import Path

from fontTools import subset

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "app" / "static" / "vendor" / "icons"
SOURCES = ("app/templates/**/*.html", "app/**/*.py", "app/static/js/*.js")
WORD = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")


def used_icons(known: dict[str, int]) -> list[str]:
    """Every word of the templates, the code and the scripts that is an icon name (names are often built at
    run time, e.g. kpi('wallet2', …) or "bi-" ~ icon, so any mention counts)."""
    words = set()
    for pattern in SOURCES:
        for path in ROOT.glob(pattern):
            words |= set(WORD.findall(path.read_text(encoding="utf-8")))
    words |= {word.removeprefix("bi-") for word in words}  # "bi-arrow-left" is one word
    return sorted(words & known.keys())


def main(package: Path) -> None:
    known = json.loads((package / "bootstrap-icons.json").read_text())
    names = used_icons(known)
    OUT.mkdir(parents=True, exist_ok=True)

    options = subset.Options()
    options.flavor = "woff2"
    font = subset.load_font(str(package / "fonts" / "bootstrap-icons.woff2"), options)
    subsetter = subset.Subsetter(options)
    subsetter.populate(unicodes=[known[name] for name in names])
    subsetter.subset(font)
    subset.save_font(font, str(OUT / "icons.woff2"), options)

    rules = "\n".join(f'.bi-{name}::before {{ content: "\\{known[name]:x}"; }}' for name in names)
    (OUT / "icons.css").write_text(f"""/* Bootstrap Icons 1.11.3 (MIT), only the icons the app uses: made by scripts/icons.py */
@font-face {{ font-display: block; font-family: "bootstrap-icons"; src: url("icons.woff2") format("woff2"); }}
.bi::before, [class^="bi-"]::before, [class*=" bi-"]::before {{
  display: inline-block; font-family: bootstrap-icons !important; font-style: normal; font-weight: normal !important;
  font-variant: normal; text-transform: none; line-height: 1; vertical-align: -.125em;
  -webkit-font-smoothing: antialiased; -moz-osx-font-smoothing: grayscale;
}}
{rules}
""")
    print(f"{len(names)} icons → {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main(Path(sys.argv[1]))
