"""The design counters of the realignment plan (docs/piano/REDESIGN_SCHERMATE.md, rounds 0–5): read only.

    python scripts/design_audit.py            # the totals
    python scripts/design_audit.py --pages    # also the templates still off the checklist, worst first

Each number should go down round after round; the goal is in the plan (0 kpi() outside the dashboard, one tab style,
at most one filled orange button per view, weights 400/600 only, four widths, fewer than 50 inline styles).
"""
from __future__ import annotations

import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TEMPLATES = ROOT / "app" / "templates"
CSS = ROOT / "app" / "static" / "css"
WIDTHS = {"576px", "768px", "992px", "1200px", "577px", "769px", "993px", "1201px"}  # and their min-width pairs
RADII = {"var(--border-radius)", "var(--border-radius-sm)", "var(--border-radius-lg)", "999px", "50%", "0"}


def _title_case(title: str) -> bool:
    """«Conti e Carte», «Gestione Assicurazioni»: more than one word starting with a capital (proper names aside)."""
    words = [w for w in re.findall(r"[A-Za-zÀ-ÿ']+", title) if len(w) > 2]
    return sum(w[0].isupper() for w in words[1:]) > 0


def main(pages: bool) -> None:
    templates = {p.relative_to(TEMPLATES).as_posix(): p.read_text(encoding="utf-8") for p in TEMPLATES.rglob("*.html")}
    css = "\n".join(p.read_text(encoding="utf-8") for p in CSS.glob("*.css"))
    everything = css + "\n".join(templates.values())

    styles = {name: len(re.findall(r'style="', text)) for name, text in templates.items()}
    # the big cards drawn outside the dashboard («Come sto» keeps them): kpi() draws a cell of the row since UI-51
    big_kpi = "kpi-card" in templates.get("partials/kpi.html", "")
    kpis = {name: text.count("kpi-card") + (text.count("kpi(") if big_kpi else 0) for name, text in templates.items()
            if not name.startswith(("dashboard/", "partials/"))}
    primaries = {name: len(re.findall(r'btn btn-primary(?![\w-])', text)) for name, text in templates.items()}
    statement = {name: text.count("statement-tab") for name, text in templates.items()}
    hand_tabs = {name: text.count('class="report-tab') for name, text in templates.items() if name != "partials/tabs.html"}
    titles = {name: m.group(1) for name, text in templates.items()
              if (m := re.search(r"{% block page_title %}{{ _\('([^']+)'\)", text))}
    weights = Counter(re.findall(r"font-weight:\s*(\d+)", everything))
    widths = Counter(re.findall(r"@media[^{]*?\(\s*(?:max|min)-width:\s*(\d+px)", css))
    # the variables are defined in theme.css; export/report.html is the printed report, with its own sheet
    pages_and_main = (CSS / "main.css").read_text(encoding="utf-8") + "\n".join(
        text for name, text in templates.items() if name != "export/report.html")
    radii = Counter(v.strip() for v in re.findall(r"border-radius:\s*([^;\"}]+)", pages_and_main))

    rows = [
        ("stili scritti a mano (style=)", sum(styles.values()), "< 50"),
        ("schede numeriche grandi fuori dalla dashboard", sum(kpis.values()), "0"),
        ("template con più di un btn-primary", sum(1 for n in primaries.values() if n > 1), "0"),
        ("statement-tabs", sum(statement.values()), "0"),
        ("schede fatte a mano (report-tab fuori da tab_bar)", sum(hand_tabs.values()), "0"),
        ("titoli in Title Case", sum(_title_case(t) for t in titles.values()), "0"),
        ("font-weight 500/700", weights["500"] + weights["700"], "0"),
        ("larghezze di ridisposizione fuori dalle 4", sum(1 for w in widths if w not in WIDTHS), "0"),
        ("raggi d'angolo fuori dalle variabili", sum(1 for r in radii if not set(r.split()) <= RADII | {"inherit"}), "0"),
        ("--clr-neutral ancora blu", int("#1971C2" in css), "0"),
    ]
    width = max(len(label) for label, _value, _goal in rows)
    for label, value, goal in rows:
        print(f"{label:<{width}}  {value:>5}   obiettivo {goal}")
    if pages:
        print("\nPagine (stili scritti a mano · kpi() · btn-primary · titolo):")
        names = sorted(templates, key=lambda n: -(styles[n] + 5 * kpis.get(n, 0) + 3 * max(primaries[n] - 1, 0)))
        for name in names[:40]:
            if styles[name] or kpis.get(name) or primaries[name] > 1 or _title_case(titles.get(name, "")):
                print(f"  {name:<48} {styles[name]:>3} · {kpis.get(name, 0):>2} · {primaries[name]} · {titles.get(name, '')}")


if __name__ == "__main__":
    main("--pages" in sys.argv)
