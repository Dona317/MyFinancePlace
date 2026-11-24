"""
The starting price database (F114): the daily closes of the instruments in data/market_seed/strumenti.csv — the
main ETFs of Borsa Italiana, the FTSE MIB, the large European and US shares, the indices, gold, oil and crypto —
read from Yahoo Finance (else Stooq, else justETF by the ISIN) from 2000, with the ECB rates since 1999, into a market store of its own, then
exported as the zip that «Importa il database di partenza» adds to the user's store.

    python scripts/build_market_seed.py                  # data/market_seed/database_di_partenza.zip
    python scripts/build_market_seed.py --since 2010     # a lighter one
    python scripts/build_market_seed.py --only VWCE.MI,ENEL.MI

It needs the internet (one request a second, only the symbols and ISINs are sent); an instrument no source answers
for is reported and left out. Run it again to bring the database up to date: what is there is kept.
"""
from __future__ import annotations

import argparse
import csv
import os
import sys
import time
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SEED = ROOT / "data" / "market_seed"
LIST = SEED / "strumenti.csv"
OUT = SEED / "database_di_partenza.zip"
STORE = SEED / "build" / "market.sqlite"   # the working store (not in the repository)


def instruments(only: set[str] | None = None) -> list[dict]:
    with LIST.open(encoding="utf-8") as handle:
        rows = [r for r in csv.DictReader(handle) if r["symbol"].strip()]
    return [r for r in rows if not only or r["symbol"] in only]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    parser.add_argument("--since", type=int, default=2000, help="first year (default 2000)")
    parser.add_argument("--only", help="comma-separated symbols")
    parser.add_argument("--pause", type=float, default=1.0, help="seconds between two requests")
    args = parser.parse_args()

    STORE.parent.mkdir(parents=True, exist_ok=True)
    os.environ["MARKET_DATABASE_URL"] = f"sqlite:///{STORE}"
    sys.path.insert(0, str(ROOT))
    from app import create_app
    from app.services import fx_store, history_filler, history_links, market_data

    app = create_app("testing") if os.environ.get("TEST_DATABASE_URL") else create_app()
    start, today = date(args.since, 1, 1), date.today()
    failed = []
    with app.app_context():
        wanted = instruments(set(args.only.split(",")) if args.only else None)
        for n, row in enumerate(wanted, 1):
            symbol, isin, name = row["symbol"].strip().upper(), row["isin"].strip() or None, row["name"].strip()
            code = (row.get("currency") or "").strip() or None  # for a source that does not say it (MSCI World)
            have = market_data.days(symbol)
            begin = max(start, max(have) - market_data.OVERLAP) if have else start
            readers = [("yahoo", market_data.read_yahoo), ("stooq", history_filler.read_stooq)]
            if isin:
                readers.append(("justetf", lambda _s, a, b, isin=isin: history_links.read_justetf(isin, a, b)))
            errors = []
            for source, reader in readers:
                try:
                    daily = reader(symbol, begin, today)
                except Exception as exc:  # noqa: BLE001 - the next source
                    errors.append(f"{source}: {str(exc)[:60]}")
                    time.sleep(args.pause)
                    continue
                if daily.points:
                    if code and not daily.currency:
                        daily = market_data.Daily(code, daily.exchange, daily.name, daily.points)
                    added = market_data.store(symbol, daily, isin, name, source=source)
                    print(f"[{n}/{len(wanted)}] {symbol}: {added} chiusure da {source} "
                          f"({daily.points[0][0]} → {daily.points[-1][0]})", flush=True)
                    break
            else:
                failed.append(symbol)
                market_data.remember_listing(symbol, isin, name)
                print(f"[{n}/{len(wanted)}] {symbol}: NON LETTO — {'; '.join(errors)}", flush=True)
            time.sleep(args.pause)
        # the ECB rates since 1999 of the main currencies (fx_store.MAIN); the others are added from Dati → Cambi
        try:
            print(f"Cambi BCE: {fx_store.store_ecb(history_filler._bytes(history_filler.ECB_HISTORY))} chiusure",
                  flush=True)
        except Exception as exc:  # noqa: BLE001 - the rest is saved all the same
            print(f"Cambi BCE NON LETTI: {exc}", flush=True)
        OUT.write_bytes(market_data.export_zip(smallest=True))
        totals = market_data.totals()
    print(f"\n{OUT}: {totals['instruments']} titoli, {totals['closes']} chiusure, "
          f"{totals['first']} → {totals['last']}, {OUT.stat().st_size / 1e6:.1f} MB")
    if failed:
        print("Non letti:", ", ".join(failed))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
