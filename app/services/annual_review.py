"""
The year in review (F23): one page — and a PDF of a few pages — with what happened to the household's money in a
year: net worth at the start and at the end and where the change came from, income, spending and savings against
the year before, the biggest categories, investment income and returns, debts repaid, goals, taxes and odd jobs,
the spending events, the contribution limits. Everything comes from the services that compute it elsewhere.
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from fpdf import FPDF

from app.models.wealth import Debt, Goal
from app.services import (
    analytics,
    contribution_limits,
    gigs,
    income_report,
    net_worth_growth,
    pdf_report,
    spending_events,
    studio,
    wealth,
)
from app.services.display import money, number

TOP_CATEGORIES = 10


def _end(year: int, today: date) -> date:
    return min(date(year, 12, 31), today)


def _change(now: float, before: float) -> float | None:
    return round((now - before) / abs(before) * 100, 1) if before else None


def _asset_lines(before: dict, after: dict) -> list[tuple[str, float, float]]:
    """(line, at the start, at the end) for every asset line of either balance sheet."""
    first = {**before["current_assets"], **before["other_assets"]}
    last = {**after["current_assets"], **after["other_assets"]}
    return [(label, first.get(label, 0.0), last.get(label, 0.0)) for label in dict.fromkeys([*first, *last])]


def review(year: int, today: date | None = None) -> dict:
    today = today or date.today()
    start, end = date(year - 1, 12, 31), _end(year, today)
    before, after = wealth.balance_sheet(start), wealth.balance_sheet(end)
    statement, previous = analytics.income_statement(year), analytics.income_statement(year - 1)
    now, then = statement["summary"], previous["summary"]

    last_year = {line["category"]: line["amount"] for line in previous["expense_lines"]}
    categories = [{"category": line["category"], "amount": line["amount"], "share": line["share"],
                   "before": last_year.get(line["category"]), "change": _change(line["amount"], last_year.get(line["category"]) or 0)}
                  for line in statement["expense_lines"][:TOP_CATEGORIES]]

    months = 12 if end.month == 12 or year < today.year else end.month
    growth = net_worth_growth.months(months, end)
    growth_total = {field: round(sum(getattr(m, field) for m in growth), 2)
                    for field in ("change", "savings", "markets", "debt_repaid", "new_assets")}
    growth_total["other"] = round(growth_total["change"] - growth_total["savings"] - growth_total["markets"]
                                  - growth_total["debt_repaid"] - growth_total["new_assets"], 2)

    debts = []
    for debt in Debt.query.order_by(Debt.name):
        owed_before = wealth.debt_summary(debt, start)["balance"]
        owed_after = wealth.debt_summary(debt, end)["balance"]
        if owed_before or owed_after:
            debts.append({"name": debt.name, "before": owed_before, "after": owed_after,
                          "repaid": round(max(owed_before - owed_after, 0), 2)})

    income = income_report.report(year, today)
    year_gigs = gigs.year(year)
    events = [s for s in spending_events.all_summaries()
              if s.event.start.year == year or (s.event.end and s.event.end.year == year)]
    # plain values only: the group's PDF reads them after leaving each archive
    return {
        "year": year, "until": end, "complete": end == date(year, 12, 31),
        "net_worth": {"start": before["net_worth"], "end": after["net_worth"],
                      "change": round(after["net_worth"] - before["net_worth"], 2),
                      "pct": _change(after["net_worth"], before["net_worth"]),
                      "lines": _asset_lines(before, after),
                      "liabilities": (before["total_liabilities"], after["total_liabilities"])},
        "growth": growth_total,
        "summary": now, "previous": then,
        "changes": {key: _change(now[key], then[key]) for key in ("income", "expenses", "net")},
        "categories": categories,
        "income": {"total": income["total"], "previous": dict(income["by_year"]).get(year - 1, Decimal(0)),
                   "holdings": [{"name": row.holding.name, "amount": row.year} for row in income["holdings"][:5] if row.year]},
        "debts": debts, "repaid": round(sum(d["repaid"] for d in debts), 2),
        "goals": [{"name": g.name, "saved": g.saved_amount, "target": g.target_amount, "progress": g.progress,
                   "completed": g.completed} for g in Goal.query.order_by(Goal.name)],
        "gigs": {"gross": year_gigs.gross, "withheld": year_gigs.withheld} if year_gigs.gross else None,
        "limits": [{"name": st.limit.name, "paid": st.paid, "yearly": st.limit.yearly, "left": st.left,
                    "deductible": st.deductible} for st in contribution_limits.all_standings(year)],
        "events": [{"name": e.event.name, "spent": e.spent, "budget": e.event.budget} for e in events],
    }


# ── PDF ────────────────────────────────────────────────────────────────────────

def _pct(value) -> str:
    return "—" if value is None else ("+" if value > 0 else "") + f"{number(value, 1)}%"


def build_pdf(data: dict, title: str | None = None, generated_at: datetime | None = None) -> bytes:
    """The review as PDF bytes, in the style of the yearly report (pdf_report)."""
    generated_at = generated_at or datetime.now()
    year = data["year"]
    title = title or f"Bilancio dell'anno {year}"
    pdf = pdf_report._ReportPDF(title)
    pdf.add_page()
    _title(pdf, title, data, generated_at)
    _body(pdf, data)
    return bytes(pdf.output())


def build_group_pdf(group, year: int, today: date | None = None, generated_at: datetime | None = None) -> bytes:
    """The review of every archive of a group (F21): the group's totals first, then one part per archive."""
    generated_at = generated_at or datetime.now()
    parts = []
    for client in sorted(group.members, key=lambda c: (not c.is_primary, c.name)):
        with studio.using(client):
            parts.append((client.name, review(year, today)))
    title = f"Bilancio dell'anno {year} · {group.name}"
    pdf = pdf_report._ReportPDF(title)
    pdf.add_page()
    first = parts[0][1] if parts else {"complete": True, "until": date(year, 12, 31)}
    _title(pdf, title, first, generated_at)
    total = {key: sum(data["net_worth"][key] for _, data in parts) for key in ("start", "end")}
    sums = {key: sum(data["summary"][key] for _, data in parts) for key in ("income", "expenses", "net")}
    pdf_report._kpis(pdf, [("Patrimonio a inizio anno", money(total["start"])), ("Patrimonio a fine periodo", money(total["end"])),
                           ("Variazione", money(total["end"] - total["start"]))])
    pdf_report._kpis(pdf, [("Entrate", money(sums["income"])), ("Uscite", money(sums["expenses"])),
                           ("Risparmio", money(sums["net"])),
                           ("Tasso di risparmio", pdf_report.percent(analytics.savings_rate(sums["income"], sums["expenses"])))])
    pdf_report._heading(pdf, "Per archivio")
    rows = [(name, money(data["net_worth"]["start"]), money(data["net_worth"]["end"]), money(data["summary"]["net"]))
            for name, data in parts]
    pdf_report._table(pdf, ["Archivio", "Inizio anno", "Fine periodo", "Risparmio"], rows, (60, 40, 40, 40))
    pdf.set_font("Helvetica", size=8)
    pdf.set_text_color(*pdf_report.MUTED)
    pdf.multi_cell(0, 4, "I passaggi di denaro tra gli archivi del gruppo restano nelle entrate e uscite di ognuno.")
    for name, data in parts:
        pdf.add_page()
        _title(pdf, f"{name} · {year}", data, generated_at)
        _body(pdf, data)
    return bytes(pdf.output())


def _body(pdf: FPDF, data: dict) -> None:
    year = data["year"]
    worth = data["net_worth"]
    pdf_report._kpis(pdf, [("Patrimonio a inizio anno", money(worth["start"])), ("Patrimonio a fine periodo", money(worth["end"])),
                           ("Variazione", f"{money(worth['change'])} ({_pct(worth['pct'])})")])
    summary = data["summary"]
    pdf_report._kpis(pdf, [("Entrate", money(summary["income"])), ("Uscite", money(summary["expenses"])),
                           ("Risparmio", money(summary["net"])), ("Tasso di risparmio", pdf_report.percent(summary["savings_rate"]))])

    pdf_report._heading(pdf, "Da dove viene la variazione del patrimonio")
    growth = data["growth"]
    rows = [("Risparmio (entrate meno uscite)", money(growth["savings"])), ("Andamento dei mercati", money(growth["markets"])),
            ("Debiti rimborsati (quota capitale)", money(growth["debt_repaid"])), ("Nuovi beni", money(growth["new_assets"])),
            ("Altro (giroconti, rettifiche)", money(growth["other"])), ("Variazione totale", money(growth["change"]))]
    pdf_report._table(pdf, None, rows, (130, 50), {len(rows) - 1: "total"})

    pdf_report._heading(pdf, "Patrimonio: inizio e fine")
    rows = [(label, money(a), money(b)) for label, a, b in worth["lines"]]
    rows.append(("Debiti", money(-worth["liabilities"][0]), money(-worth["liabilities"][1])))
    rows.append(("Patrimonio netto", money(worth["start"]), money(worth["end"])))
    pdf_report._table(pdf, ["Voce", f"31/12/{year - 1}", data["until"].strftime("%d/%m/%Y")], rows, (90, 45, 45),
                      {len(rows) - 1: "total"})

    pdf_report._heading(pdf, f"Entrate e uscite rispetto al {year - 1}")
    previous, changes = data["previous"], data["changes"]
    rows = [("Entrate", money(previous["income"]), money(summary["income"]), _pct(changes["income"])),
            ("Uscite", money(previous["expenses"]), money(summary["expenses"]), _pct(changes["expenses"])),
            ("Risparmio", money(previous["net"]), money(summary["net"]), _pct(changes["net"]))]
    pdf_report._table(pdf, ["", str(year - 1), str(year), "Variazione"], rows, (60, 40, 40, 40))

    if data["categories"]:
        pdf_report._heading(pdf, "Le spese più grandi")
        rows = [(c["category"], money(c["amount"]), pdf_report.percent(c["share"]),
                 money(c["before"]) if c["before"] is not None else "—", _pct(c["change"])) for c in data["categories"]]
        pdf_report._table(pdf, ["Categoria", str(year), "% uscite", str(year - 1), "Variazione"], rows, (60, 32, 26, 32, 30))

    rows = [("Rendite (dividendi, cedole, interessi)", money(data["income"]["total"]))]
    if data["repaid"]:
        rows.append(("Debiti rimborsati", money(data["repaid"])))
    if data["gigs"]:
        rows += [("Lavori occasionali: lordo", money(data["gigs"]["gross"])),
                 ("Ritenute d'acconto subite", money(data["gigs"]["withheld"]))]
    for limit in data["limits"]:
        rows.append((f"{limit['name']}: versato", f"{money(limit['paid'])} su {money(limit['yearly'])}"))
    pdf_report._heading(pdf, "Investimenti, debiti, fisco")
    pdf_report._table(pdf, None, rows, (120, 60))

    if data["goals"]:
        pdf_report._heading(pdf, "Obiettivi")
        rows = [(g["name"], money(g["saved"]), money(g["target"]), f"{number(g['progress'], 0)}%") for g in data["goals"]]
        pdf_report._table(pdf, ["Obiettivo", "Messo da parte", "Traguardo", "Fatto"], rows, (80, 35, 35, 30))

    if data["events"]:
        pdf_report._heading(pdf, "Eventi")
        rows = [(e["name"], money(e["spent"]), money(e["budget"]) if e["budget"] else "—") for e in data["events"]]
        pdf_report._table(pdf, ["Evento", "Speso", "Budget"], rows, (100, 40, 40))


def _title(pdf: FPDF, title: str, data: dict, generated_at: datetime) -> None:
    pdf.set_font("Helvetica", "B", 18)
    pdf.set_text_color(*pdf_report.INK)
    pdf.cell(0, 9, title, new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", size=9)
    pdf.set_text_color(*pdf_report.MUTED)
    period = "" if data["complete"] else f" · fino al {data['until']:%d/%m/%Y}"
    pdf.cell(0, 5, f"MyFinancePlace{period} · generato il {generated_at:%d/%m/%Y %H:%M}", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(5)
