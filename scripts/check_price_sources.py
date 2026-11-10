"""
Check, from the user's computer, which end-of-day price sources still answer (F69, D10).

The development sandbox cannot reach these sites, so this script is run on the user's PC:

    python scripts/check_price_sources.py
    python scripts/check_price_sources.py --etf IE00B4L5Y983 --bond IT0005083057 --fund IE00B03HCZ61

Only the standard library is used. Each answer is saved under samples/price_sources/<date>/ (to write offline tests
from real pages) and a summary is written to report.md in the same folder. Nothing but ISINs and tickers is sent,
with at most one request a second per site. The script always says who it is (the app's own user agent) and never
tries to get past an anti-bot wall, a login or a token: a source behind one is reported as blocked, and that is the
answer (such a source does not go into the app).
"""
from __future__ import annotations

import argparse
import gzip
import io
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

APP_AGENT = "Mozilla/5.0 (compatible; MyFinancePlace)"
TIMEOUT = 20
ROOT = Path(__file__).resolve().parent.parent


@dataclass
class Check:
    number: int
    name: str
    url: str
    status: str = "-"
    outcome: str = "non provato"
    detail: str = ""
    seconds: float = 0.0
    saved: list[str] = field(default_factory=list)


class Client:
    """One request a second per host, every answer saved to disk."""

    def __init__(self, folder: Path):
        self.folder = folder
        self.opener = urllib.request.build_opener()
        self.last: dict[str, float] = {}

    def get(self, check: Check, url: str, name: str, data: bytes | None = None,
            headers: dict | None = None) -> tuple[int, bytes, str]:
        host = urllib.parse.urlsplit(url).hostname or ""
        pause = self.last.get(host, 0.0) + 1.0 - time.monotonic()
        if pause > 0:
            time.sleep(pause)
        all_headers = {"User-Agent": APP_AGENT, "Accept": "application/json, text/html, */*",
                       "Accept-Language": "it-IT,it;q=0.9", "Accept-Encoding": "gzip"}
        all_headers.update(headers or {})
        request = urllib.request.Request(url, data=data, headers=all_headers, method="POST" if data else "GET")
        started = time.monotonic()
        try:
            with self.opener.open(request, timeout=TIMEOUT) as response:
                code, body, final = response.status, response.read(), response.geturl()
                if response.headers.get("Content-Encoding") == "gzip":
                    body = gzip.decompress(body)
        except urllib.error.HTTPError as error:
            code, body, final = error.code, error.read() or b"", url
        finally:
            self.last[host] = time.monotonic()
            check.seconds += time.monotonic() - started
        path = self.folder / f"{check.number:02d}_{name}"
        path.write_bytes(body)
        check.saved.append(path.name)
        return code, body, final


def text(body: bytes) -> str:
    return body.decode("utf-8", errors="replace")


def challenge(body: bytes) -> str | None:
    """The name of the anti-bot wall a page looks like, if any."""
    page = text(body[:20000]).lower()
    for marker, name in (("cf-chl", "Cloudflare"), ("just a moment", "Cloudflare"), ("incapsula", "Imperva"),
                         ("_incapsula_resource", "Imperva"), ("awswaf", "AWS WAF"), ("captcha", "captcha"),
                         ("verify your browser", "verifica JavaScript")):
        if marker in page:
            return name
    return None


def run(check: Check, client: Client, steps) -> None:
    try:
        steps(check, client)
    except (urllib.error.URLError, TimeoutError, OSError) as error:
        check.outcome, check.detail = "errore di rete", str(getattr(error, "reason", error))[:200]
    except (ValueError, KeyError, IndexError, TypeError) as error:
        check.outcome, check.detail = "risposta inattesa", f"{type(error).__name__}: {error}"[:200]


def judge(check: Check, code: int, body: bytes, ok: bool, detail: str) -> None:
    check.status = str(code)
    wall = challenge(body)
    if ok:
        check.outcome, check.detail = "OK", detail
    elif wall:
        check.outcome, check.detail = f"bloccato ({wall})", detail
    else:
        check.outcome, check.detail = "non funziona", detail or text(body[:160]).replace("\n", " ")


def main() -> int:
    parser = argparse.ArgumentParser(description="Prova le fonti dei prezzi di fine giornata (F69).")
    parser.add_argument("--etf", default="IE00B4L5Y983", help="ISIN di un ETF (default: iShares Core MSCI World)")
    parser.add_argument("--etf-ticker", default="SWDA.MI", help="ticker Yahoo dello stesso ETF")
    parser.add_argument("--bond", default="IT0005083057", help="ISIN di un BTP quotato al MOT")
    parser.add_argument("--fund", default="IE00B03HCZ61", help="ISIN di un fondo comune")
    parser.add_argument("--yahoo", default="SWDA.MI,VWCE.DE,EUNL.DE,CSSPX.MI,ENI.MI,ISP.MI,UCG.MI,MEUD.PA,IWDA.AS,"
                        "XDWD.DE", help="ticker Yahoo da scaricare di fila (5 anni, giornaliero)")
    args = parser.parse_args()

    folder = ROOT / "samples" / "price_sources" / date.today().isoformat()
    folder.mkdir(parents=True, exist_ok=True)
    client = Client(folder)
    year_ago = (date.today() - timedelta(days=365)).isoformat()
    checks: list[Check] = []
    found: dict[str, str] = {}

    def add(name: str, url: str, steps) -> None:
        check = Check(len(checks) + 1, name, url)
        checks.append(check)
        print(f"[{check.number:2d}] {name} …", flush=True)
        run(check, client, steps)
        print(f"     {check.outcome} {check.detail}", flush=True)

    # 1. The search the app uses today for Morningstar.
    url1 = f"https://www.morningstar.it/it/util/SecuritySearch.ashx?q={args.fund}&limit=5"

    def morningstar_www(check, c):
        code, body, final = c.get(check, url1, "morningstar_www_search.txt")
        lines = [line for line in text(body).splitlines() if "|" in line]
        moved = "" if final == url1 else f"reindirizzato a {final}"
        judge(check, code, body, code == 200 and bool(lines), f"{len(lines)} risultati {moved}".strip())
    add("Morningstar www (ricerca usata oggi)", url1, morningstar_www)

    # 2. Morningstar lt.: ISIN -> SecId.
    url2 = ("https://lt.morningstar.com/api/rest.svc/klr5zyak8x/security/screener?page=1&pageSize=10&outputType=json"
            "&universeIds=FOALL%24%24ALL%7CETALL%24%24ALL&securityDataPoints=SecId%7CName%7Cisin%7CcurrencyId"
            f"&term={args.fund}")

    def morningstar_lt_search(check, c):
        code, body, _ = c.get(check, url2, "morningstar_lt_screener.json")
        rows = json.loads(text(body)).get("rows", []) if code == 200 else []
        exact = [row for row in rows if row.get("isin") == args.fund] or rows
        if exact:
            found["secid"] = exact[0]["SecId"]
        judge(check, code, body, bool(exact),
              f"SecId {exact[0].get('SecId')} valuta {exact[0].get('currencyId')}" if exact else "nessuna riga")
    add("Morningstar lt. screener (ISIN → SecId)", url2, morningstar_lt_search)

    # 3. Morningstar lt.: daily NAV history, with the two tokens seen in 2026.
    for token in ("ok91jeenoo", "t92wz0sj7c"):
        url3 = (f"https://lt.morningstar.com/api/rest.svc/timeseries_price/{token}?id={{secid}}%5D2%5D1%5D"
                f"&currencyId=EUR&idtype=Morningstar&frequency=daily&startDate={year_ago}&outputType=COMPACTJSON")

        def morningstar_history(check, c, token=token, url3=url3):
            if "secid" not in found:
                check.outcome, check.detail = "non provato", "manca il SecId della prova 2"
                return
            url = url3.format(secid=found["secid"])
            check.url = url
            code, body, _ = c.get(check, url, f"morningstar_lt_timeseries_{token}.json")
            points = json.loads(text(body)) if code == 200 and text(body).strip().startswith("[") else []
            last = points[-1] if points else None
            judge(check, code, body, len(points) > 100,
                  f"{len(points)} giorni, ultimo {last}" if last else "serie vuota")
        add(f"Morningstar lt. storico NAV (token {token})", url3, morningstar_history)

    # 4. Yahoo chart, the app's main source, several tickers in a row (does it start answering 429?).
    tickers = [t.strip() for t in args.yahoo.split(",") if t.strip()]
    url4 = "https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?range=5y&interval=1d"

    def yahoo(check, c):
        good, refused, codes = 0, 0, []
        for ticker in tickers:
            code, body, _ = c.get(check, url4.format(ticker=ticker), f"yahoo_{ticker}.json")
            codes.append(code)
            if code == 429:
                refused += 1
            elif code == 200:
                result = json.loads(text(body))["chart"]["result"][0]
                good += len(result.get("timestamp") or []) > 1000
        check.status = ",".join(sorted({str(x) for x in codes}))
        check.outcome = "OK" if good == len(tickers) else ("limitato (429)" if refused else "parziale")
        check.detail = f"{good}/{len(tickers)} serie di 5 anni, {refused} rifiutate con 429"
    add(f"Yahoo chart, {len(tickers)} ticker di fila", url4, yahoo)

    # 5. Stooq, the app's backup today.
    for name, url5 in (("ultimo prezzo", "https://stooq.com/q/l/?s=eunl.de&f=sd2t2ohlcv&h&e=csv"),
                       ("storico", "https://stooq.com/q/d/l/?s=eunl.de&i=d")):
        def stooq(check, c, url5=url5, name=name):
            code, body, _ = c.get(check, url5, f"stooq_{name.replace(' ', '_')}.csv")
            rows = [r for r in text(body).splitlines() if re.match(r"\d{4}-\d{2}-\d{2}|EUNL", r, re.I)]
            judge(check, code, body, code == 200 and bool(rows), f"{len(rows)} righe CSV")
        add(f"Stooq {name}", url5, stooq)

    # 6. Borsa Italiana chart API, asked plainly: if it wants a token or a WAF cookie, it is not usable as it is.
    url6 = f"https://grafici.borsaitaliana.it/api/instruments/{args.bond},MOTX,ISIN/history/period?period=1Y"

    def borsa(check, c):
        code, body, _ = c.get(check, url6, "borsaitaliana_history.json")
        days = (json.loads(text(body)).get("history") or {}).get("historyDt") or [] if code == 200 else []
        why = "chiede un token o un cookie: non usabile così" if code in (401, 403) else ""
        judge(check, code, body, len(days) > 100, f"{len(days)} giorni {why}".strip())
    add("Borsa Italiana API grafici (BTP sul MOT)", url6, borsa)

    # 7. justETF performance chart.
    url7 = (f"https://www.justetf.com/api/etfs/{args.etf}/performance-chart?locale=it&currency=EUR"
            f"&valuesType=MARKET_VALUE&reduceData=false&includeDividends=false&dateFrom={year_ago}"
            f"&dateTo={date.today().isoformat()}")

    def justetf(check, c):
        code, body, _ = c.get(check, url7, "justetf_chart.json")
        series = json.loads(text(body)).get("series", []) if code == 200 else []
        judge(check, code, body, len(series) > 100, f"{len(series)} punti")
    add("justETF performance-chart", url7, justetf)

    # 8. Financial Times: search by ISIN, then the daily series.
    url8 = f"https://markets.ft.com/data/searchapi/searchsecurities?query={args.fund}"

    def ft(check, c):
        code, body, _ = c.get(check, url8, "ft_search.json")
        items = json.loads(text(body)).get("data", {}).get("security", []) if code == 200 else []
        if not items:
            judge(check, code, body, False, "nessun risultato")
            return
        xid = items[0].get("xid")
        payload = json.dumps({"days": 365, "dataPeriod": "Day", "dataInterval": 1, "timeServiceFormat": "JSON",
                              "returnDateType": "ISO8601", "elements": [{"Type": "price", "Symbol": xid}]}).encode()
        code, body, _ = c.get(check, "https://markets.ft.com/data/chartapi/series", "ft_series.json",
                              data=payload, headers={"Content-Type": "application/json"})
        dates = json.loads(text(body)).get("Dates", []) if code == 200 else []
        judge(check, code, body, len(dates) > 100, f"xid {xid}, {len(dates)} giorni")
    add("Financial Times (fondi)", url8, ft)

    # 9. investing.com: only to know whether it answers; it is not going into the app.
    url9 = f"https://endpoints.investing.com/pd-instruments/v1/instruments/search?query={args.etf}&domain_id=1"

    def investing(check, c):
        code, body, _ = c.get(check, url9, "investing_search.json")
        judge(check, code, body, code == 200 and text(body).lstrip().startswith(("{", "[")),
              "solo diagnosi: non verrà integrato")
    add("investing.com ricerca (solo diagnosi)", url9, investing)

    # 10. ECB: the whole history of reference rates.
    url10 = "https://www.ecb.europa.eu/stats/eurofxref/eurofxref-hist.zip"

    def ecb(check, c):
        code, body, _ = c.get(check, url10, "ecb_eurofxref_hist.zip")
        rows = 0
        if code == 200:
            with zipfile.ZipFile(io.BytesIO(body)) as archive:
                rows = len(archive.read(archive.namelist()[0]).splitlines())
        judge(check, code, body, rows > 1000, f"{len(body) // 1024} KB, {rows} giorni, {check.seconds:.1f} s")
    add("BCE cambi storici completi", url10, ecb)

    # 11. Börse Frankfurt: latest price by ISIN on XETRA (used by Wealthfolio, no key).
    url11 = f"https://api.live.deutsche-boerse.com/v1/data/price_information/single?isin={args.etf}&mic=XETR"

    def frankfurt(check, c):
        code, body, _ = c.get(check, url11, "boerse_frankfurt_price.json")
        judge(check, code, body, code == 200 and "lastPrice" in text(body), text(body[:120]).replace("\n", " "))
    add("Börse Frankfurt ultimo prezzo (XETRA)", url11, frankfurt)

    lines = [f"# Prova delle fonti dei prezzi — {date.today().isoformat()}", "",
             f"ETF {args.etf} ({args.etf_ticker}) · BTP {args.bond} · fondo {args.fund}", "",
             "| # | Prova | HTTP | Esito | Dettaglio | Secondi |", "|---|---|---|---|---|---|"]
    for check in checks:
        lines.append(f"| {check.number} | {check.name} | {check.status} | {check.outcome} | "
                     f"{check.detail.replace('|', '/')} | {check.seconds:.1f} |")
    lines += ["", f"Risposte salvate in `{folder.relative_to(ROOT)}`."]
    (folder / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n" + "\n".join(lines))
    print(f"\nRiepilogo: {folder / 'report.md'} — mandalo (o incollalo) all'assistente.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
