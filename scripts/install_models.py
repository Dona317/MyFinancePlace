"""
Prepare local AI models (Ollama) for reading bank statements.

    python scripts/install_models.py --list                  # catalog, with what is already installed
    python scripts/install_models.py --recommended           # qwen2.5vl:7b (best under 10 GB)
    python scripts/install_models.py --tier piccolo --vision # every small model that reads scans/photos
    python scripts/install_models.py gemma3:4b llama3.2:1b   # specific models
    python scripts/install_models.py --tier tiny --dry-run   # only print the `ollama pull` commands

Requires Ollama (https://ollama.com/download) running locally, or --url for another machine.
"""
import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.services.ai_models import CATALOG, TIERS, OllamaError, _request, status  # noqa: E402

RECOMMENDED = ["qwen2.5vl:7b"]


def print_catalog(installed: dict) -> None:
    for tier, label in TIERS.items():
        print(f"\n{label}")
        for m in (m for m in CATALOG if m.tier == tier):
            mark = "installato" if m.name in installed else ""
            reads = "scansioni/foto" if m.vision else "solo testo"
            print(f"  {m.name:<22} {m.family:<6} ~{m.size_gb:>4.1f} GB  RAM {m.ram_gb:>2} GB  {reads:<15} {mark}")


def pull(url: str, name: str) -> bool:
    print(f"\n==> {name}")
    try:
        with _request(url, "/api/pull", method="POST", body={"model": name, "stream": True}, timeout=3600) as response:
            last = ""
            for line in response:
                event = json.loads(line) if line.strip() else {}
                if "error" in event:
                    raise OllamaError(event["error"])
                text = event.get("status", "")
                if event.get("total"):
                    text += f" {int(event.get('completed', 0) * 100 / event['total'])}%"
                if text != last:
                    print(f"\r    {text:<60}", end="", flush=True)
                    last = text
        print("\r    completato" + " " * 50)
        return True
    except OllamaError as exc:
        print(f"\n    ERRORE: {exc}")
        return False


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("models", nargs="*", help="nomi dei modelli da installare")
    parser.add_argument("--list", action="store_true", help="mostra il catalogo")
    parser.add_argument("--recommended", action="store_true", help="installa il modello consigliato")
    parser.add_argument("--tier", choices=list(TIERS), help="tutti i modelli di una taglia")
    parser.add_argument("--vision", action="store_true", help="solo modelli che leggono scansioni e foto")
    parser.add_argument("--dry-run", action="store_true", help="stampa i comandi senza scaricare")
    parser.add_argument("--url", default=os.environ.get("OLLAMA_URL", "http://localhost:11434"))
    args = parser.parse_args()

    names = list(args.models) + (RECOMMENDED if args.recommended else [])
    if args.tier:
        names += [m.name for m in CATALOG if m.tier == args.tier and (m.vision or not args.vision)]
    elif args.vision and not names:
        names += [m.name for m in CATALOG if m.vision]
    names = list(dict.fromkeys(names))

    if args.dry_run:
        for name in names:
            print(f"ollama pull {name}")
        return 0

    state = status(args.url)
    if args.list or not names:
        if not state["running"]:
            print(state["error"])
        print_catalog(state["installed"])
        if not names:
            print("\nNessun modello scelto: usa --recommended, --tier o i nomi dei modelli (vedi --help).")
        return 0
    if not state["running"]:
        print(state["error"])
        return 1

    todo = [n for n in names if n not in state["installed"]]
    for name in sorted(set(names) - set(todo)):
        print(f"{name}: già installato")
    failed = [name for name in todo if not pull(args.url, name)]
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
