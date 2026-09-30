"""
Interface translations (Italian is the source language, English the translation).

    python scripts/translations.py update    # after changing texts: extract them and update app/translations/en
    python scripts/translations.py compile   # rebuild the .mo files the app reads (also run by the tests' check)

Texts are marked with _() / ngettext() in templates and Python, _l() for labels defined at import time and
N_() for words that are also stored as data (shown with the |tr filter).
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TRANSLATIONS = ROOT / "app" / "translations"
POT = TRANSLATIONS / "messages.pot"


def run(*args: str) -> None:
    subprocess.run([sys.executable, "-m", "babel.messages.frontend", *args], check=True, cwd=ROOT)


def update() -> None:
    run("extract", "-F", "babel.cfg", "-k", "_l", "-k", "N_", "--no-location", "--sort-output",
        "--project", "MyFinancePlace", "-o", str(POT), ".")
    run("update", "-i", str(POT), "-d", str(TRANSLATIONS), "--no-fuzzy-matching", "--ignore-obsolete")


def compile_() -> None:
    run("compile", "-d", str(TRANSLATIONS), "--statistics")


if __name__ == "__main__":
    {"update": update, "compile": compile_}[sys.argv[1] if len(sys.argv) > 1 else "compile"]()
