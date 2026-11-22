"""
Check an Enable Banking application against the real API, step by step, with the app's own client (F107).

    python scripts/psd2_sandbox_check.py --app-id <ID> --key <file.pem>                      # 1-3: application, banks, consent link
    python scripts/psd2_sandbox_check.py --app-id <ID> --key <file.pem> --code <code>        # 4-5: session, accounts, movements

1. GET /application  — the credentials work (name, environment, redirect URLs registered, active?)
2. GET /aspsps       — the banks of the country (the sandbox has «Mock ASPSP»)
3. POST /auth        — the link to the bank's page; open it, give the consent, copy `code` from the address it returns to
4. POST /sessions    — the consent becomes a session with its accounts
5. GET balances and transactions of each account — what the bank really sends (fields, statuses, MCC…)

Nothing is saved; the key is read from the file and never printed.
"""
import argparse
import json
import sys
import uuid
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from flask import Flask  # noqa: E402

from app.services.open_banking import client  # noqa: E402
from app.services.open_banking.sync import provider_ref, to_rows  # noqa: E402


def step(title: str) -> None:
    print(f"\n── {title} " + "─" * max(0, 70 - len(title)))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--app-id", required=True)
    parser.add_argument("--key", required=True, help="the application's private key (.pem)")
    parser.add_argument("--country", default="FI")
    parser.add_argument("--aspsp", default="Mock ASPSP")
    parser.add_argument("--redirect", default="https://localhost/banking/callback",
                        help="one of the redirect URLs registered in the application")
    parser.add_argument("--code", help="the code the bank returned (step 4-5)")
    parser.add_argument("--days", type=int, default=90)
    args = parser.parse_args(argv)
    creds = client.Credentials(args.app_id, Path(args.key).read_text(encoding="utf-8"))
    app = Flask("psd2-check")
    with app.app_context():
        try:
            if args.code:
                return _session(creds, args)
            return _consent(creds, args)
        except client.ProviderError as exc:
            print(f"\n✗ Enable Banking ha risposto: HTTP {exc.status} {exc.code or ''} — {exc}")
            return 1


def _consent(creds, args) -> int:
    step("1. Applicazione")
    info = client.application(creds)
    print(json.dumps({k: info.get(k) for k in ("name", "environment", "active", "redirect_urls", "kid") if k in info},
                     indent=2, ensure_ascii=False) or info)
    step(f"2. Banche in {args.country}")
    banks = client.aspsps(creds, args.country)
    names = [b.get("name") for b in banks]
    print(f"{len(banks)} banche; prime: {', '.join(names[:12])}")
    if args.aspsp not in names:
        print(f"✗ «{args.aspsp}» non c'è in {args.country}: scegline una con --aspsp")
        return 1
    step("3. Link per il consenso")
    until = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=10)
    answer = client.start_authorization(creds, args.aspsp, args.country, args.redirect, str(uuid.uuid4()), until)
    print("Apri questo indirizzo, dai il consenso, poi copia il valore di `code` dall'indirizzo a cui torni:")
    print(answer.get("url"))
    return 0


def _session(creds, args) -> int:
    step("4. Sessione")
    session = client.create_session(creds, args.code)
    accounts = session.get("accounts") or []
    print(f"sessione creata, consenso fino al {(session.get('access') or {}).get('valid_until')}, {len(accounts)} conti")
    for account in accounts:
        uid = account.get("uid")
        print(f"\n• {account.get('name')} {(account.get('account_id') or {}).get('iban') or ''} {account.get('currency')}")
        step(f"5. Saldi e movimenti degli ultimi {args.days} giorni")
        for balance in client.balances(creds, uid):
            print(f"  saldo {balance.get('balance_type')}: {(balance.get('balance_amount') or {}).get('amount')}")
        items = client.transactions(creds, uid, date.today() - timedelta(days=args.days))
        found = to_rows(items, uid)
        fields = Counter(key for item in items for key, value in item.items() if value not in (None, "", [], {}))
        print(f"  {len(items)} movimenti: {len(found.rows)} contabilizzati, {found.pending} in attesa")
        print(f"  con id della banca: {sum(1 for i in items if provider_ref(i, uid))}/{len(items)}")
        print("  campi presenti (quante volte): " + ", ".join(f"{k} {v}" for k, v in fields.most_common()))
        for row in found.rows[:5]:
            print(f"  {row.date} {row.amount:>10} {row.description[:50]} | {row.details or ''} | MCC→{row.bank_category}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
