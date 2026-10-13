"""
The assistant on the user's data (F20): a question in plain Italian, answered by the AI model already configured
(local Ollama, or Anthropic when chosen in Settings → AI) from a summary of the archive.

Read only by construction: the model receives a summary of numbers computed here (balances, spending by category
and month, investments, debts, goals, events, passive income, data problems) and can only answer, with links to the
pages where the numbers are. It never sees single movements and cannot change anything.
"""
from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date

from flask import url_for
from flask_babel import gettext as _

from app.models.account import Account
from app.models.wealth import Debt, Goal
from app.services import (
    accounts,
    ai_classification,
    ai_extraction,
    analytics,
    categories,
    data_health,
    income_report,
    periods,
    personal_loans,
    spending_events,
    wealth,
)
from app.services.ai_extraction import AIExtractionError
from app.services.spending_rhythm import by_category

MAX_QUESTION = 500

SYSTEM_PROMPT = """Sei l'assistente finanziario personale di una famiglia italiana, dentro la loro app MyFinancePlace.
Rispondi in italiano, in modo breve e concreto, usando SOLO i dati nel riassunto che ricevi (in euro).
Se il riassunto non basta per rispondere, dillo e indica quale pagina guardare. Non inventare numeri.
Scrivi gli importi all'italiana (1.234,56 €). Niente consigli d'investimento personalizzati: puoi spiegare i numeri.
In "links" metti le pagine dell'app utili per approfondire, scegliendole dall'elenco consentito."""

PAGES = {
    "transactions": ("transactions.index", "Transazioni"),
    "reports": ("reports.index", "Report"),
    "rhythm": ("reports.rhythm", "Ritmo della spesa"),
    "budget": ("lifestyle.budget", "Budget"),
    "goals": ("lifestyle.goals", "Obiettivi"),
    "events": ("events.index", "Eventi"),
    "portfolio": ("portfolio.index", "Portafoglio"),
    "performance": ("portfolio.performance_page", "Rendimenti"),
    "income": ("portfolio.income", "Rendite"),
    "debt": ("debt.index", "Debiti"),
    "balance_sheet": ("accounting.balance_sheet", "Stato patrimoniale"),
    "growth": ("accounting.growth", "Crescita del patrimonio"),
    "retirement": ("forecast.retirement", "Pensione e FIRE"),
    "health": ("health.index", "Salute dei dati"),
}


@dataclass
class Answer:
    question: str
    text: str
    links: list[tuple[str, str]] = field(default_factory=list)  # (label, url)


def available() -> bool:
    return ai_extraction.provider() is not None


def leaves_computer() -> bool:
    return ai_extraction.provider() == "anthropic"


def facts(today: date | None = None) -> dict:
    """The summary the model answers from: numbers only, no single movement."""
    today = today or date.today()
    sheet = wealth.balance_sheet()
    trailing = analytics.last_12_months(today)
    start = periods.add_months(periods.first_of_month(today), -11)
    by_month = defaultdict(dict)
    for back in range(3):
        month_start = periods.add_months(periods.first_of_month(today), -back)
        month_end = periods.add_months(month_start, 1).replace(day=1)
        spent = by_category(month_start, min(today, month_end))
        by_month[month_start.strftime("%Y-%m")] = {k: round(float(v), 2) for k, v in sorted(spent.items(), key=lambda kv: -kv[1])[:12]}
    year = by_category(start, today)
    income = income_report.report(today.year, today)
    return {
        "oggi": today.isoformat(),
        "patrimonio": {"netto": sheet["net_worth"], "liquidita": sheet["cash"], "investimenti": sheet["investments"],
                       "totale_attivita": sheet["total_assets"], "totale_debiti": sheet["total_liabilities"]},
        "conti": [{"nome": a.name, "tipo": a.kind, "saldo": round(accounts.balance(a), 2)}
                  for a in Account.query.filter_by(active=True).order_by(Account.name)],
        "ultimi_12_mesi": {"mesi": trailing["labels"], "entrate": [round(v, 2) for v in trailing["income"]],
                           "uscite": [round(v, 2) for v in trailing["expenses"]]},
        "spese_12_mesi_per_categoria": {k: round(float(v), 2) for k, v in sorted(year.items(), key=lambda kv: -kv[1])[:20]},
        "spese_per_categoria_ultimi_3_mesi": dict(by_month),
        "investimenti": [{"nome": h.name, "classe": h.asset_class, "valore": round(h.value, 2),
                          "guadagno_pct": round(h.gain_pct, 1)} for h in wealth.holdings_on()][:40],
        "rendite": {"ultimi_12_mesi": float(income["last_12"]), "anno_corrente": float(income["total"])},
        "debiti": [{"nome": d.name, "tipo": d.type, "residuo": wealth.debt_summary(d)["balance"],
                    "tasso": float(d.annual_rate or 0)} for d in Debt.query.order_by(Debt.name)],
        "obiettivi": [{"nome": g.name, "obiettivo": float(g.target_amount), "risparmiato": float(g.saved_amount),
                       "entro": g.target_date.isoformat() if g.target_date else None} for g in Goal.query.all()],
        "eventi": [{"nome": s.event.name, "costo": float(s.net), "budget": float(s.event.budget) if s.event.budget else None}
                   for s in spending_events.all_summaries()][:15],
        "prestiti_tra_persone": [{"persona": p.name, "saldo": float(p.balance), "nota": "positivo: ti deve"}
                                 for p in personal_loans.people() if p.balance][:15],
        "problemi_nei_dati": [{"controllo": c.title, "quanti": c.count} for c in data_health.severe(today)],
        "categoria_senza_nome": categories.FALLBACK,
    }


def _schema() -> dict:
    return {
        "type": "object",
        "properties": {
            "answer": {"type": "string"},
            "links": {"type": "array", "items": {"type": "string", "enum": list(PAGES)}},
        },
        "required": ["answer", "links"],
        "additionalProperties": False,
    }


def _ask_model(prompt: str) -> str:
    model = ai_classification.model_name()  # a text model: the one that classifies movements
    if ai_extraction.provider() == "anthropic":
        return ai_extraction.anthropic_json(model, SYSTEM_PROMPT, [{"type": "text", "text": prompt}], _schema(),
                                            max_tokens=4000, too_long=_("Domanda o dati troppo lunghi."))
    return ai_extraction.ollama_json(model, SYSTEM_PROMPT, prompt, _schema())


def ask(question: str, today: date | None = None) -> Answer:
    question = " ".join((question or "").split())[:MAX_QUESTION]
    if not question:
        raise AIExtractionError(_("Scrivi una domanda."))
    if not available():
        raise AIExtractionError(_("Nessun modello AI configurato: sceglilo in Impostazioni → AI."))
    prompt = (f"Riassunto dei dati della famiglia (JSON):\n{json.dumps(facts(today), ensure_ascii=False)}\n\n"
              f"Domanda: {question}")
    reply = _ask_model(prompt)
    try:
        data = json.loads(reply or "")
    except (TypeError, json.JSONDecodeError):
        raise AIExtractionError(_("Il modello non ha dato una risposta leggibile: riprova."))
    text = str(data.get("answer") or "").strip() if isinstance(data, dict) else ""
    if not text:
        raise AIExtractionError(_("Il modello non ha dato una risposta leggibile: riprova."))
    keys = [k for k in dict.fromkeys(data.get("links") or []) if k in PAGES]
    return Answer(question, text, [(_(PAGES[k][1]), url_for(PAGES[k][0])) for k in keys])
