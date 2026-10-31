"""
The review of the transactions register: reads the transactions on screen and points out the probable mistakes,
each with the change it suggests. Nothing changes until the user applies a suggestion.

Checks, the first that applies to a transaction wins:
- a cash withdrawal or deposit that is not yet a transfer with the «Contanti» account (cash);
- an income booked as an expense, or a payment booked as an income (type);
- an investment booked as an expense instead of a transfer (type → transfer);
- a category that the user's rules or the AI read differently from the causale (category).
"""
from dataclasses import dataclass

from app.models.transaction import Transaction
from app.services import ai_classification, cash, category_rules
from app.services.ai_extraction import AIExtractionError
from app.services.i18n import tr
from app.services.parsing import normalize
from flask_babel import gettext as _

INCOME_WORDS = ("stipendio", "emolumenti", "accredito", "bonifico a tuo favore", "rimborso", "interessi attivi")
EXPENSE_WORDS = ("pagamento pos", "addebito", "acquisto", "bolletta", "affitto", "commissioni")
INVEST_WORDS = ("etf", "titoli", "investimento", "fondo comune", "broker", "trading", "acquisto titoli")
AI_LIMIT = 40  # transactions the AI reads in one review: keeps a cloud review short and cheap


@dataclass
class Finding:
    tx: Transaction
    kind: str    # "type" | "category" | "cash"
    value: str   # the new type, the new category, or "" for cash
    title: str
    reason: str

    @property
    def token(self) -> str:
        """What the form sends back for this suggestion: «transaction id | kind | value»."""
        return f"{self.tx.id}|{self.kind}|{self.value}"


def _has(text: str, words: tuple[str, ...]) -> bool:
    """Whether one of the (normalized) words appears in the normalized text."""
    return any(word in text for word in words)


def _text(tx: Transaction) -> str:
    return normalize(" ".join(t for t in (tx.description, tx.bank_description, tx.counterparty) if t))


def _first_check(tx: Transaction, cash_exists: bool) -> Finding | None:
    text = _text(tx)
    if cash_exists and cash.withdrawal_or_deposit(tx):
        kind = _("prelievo") if cash.withdrawal_or_deposit(tx) == "withdrawal" else _("versamento")
        return Finding(tx, "cash", "", _("%(kind)s dalla banca: è un giroconto con Contanti", kind=kind),
                       _("Il denaro passa dal conto alla cassa: non è una spesa né un'entrata."))
    if tx.type == "expense" and _has(text, INCOME_WORDS) and not _has(text, EXPENSE_WORDS):
        return Finding(tx, "type", "income", _("Probabile entrata registrata come uscita"),
                       _("La causale parla di un accredito o di uno stipendio."))
    if tx.type == "income" and _has(text, EXPENSE_WORDS) and not _has(text, INCOME_WORDS):
        return Finding(tx, "type", "expense", _("Probabile uscita registrata come entrata"),
                       _("La causale parla di un pagamento o di un addebito."))
    if tx.type == "expense" and _has(text, INVEST_WORDS):
        return Finding(tx, "type", "transfer", _("Investimento registrato come spesa"),
                       _("Un investimento è un giroconto verso il conto titoli: non riduce il patrimonio."))
    return None


def review(transactions: list[Transaction], categories: list[str]) -> tuple[list[Finding], str | None]:
    """The suggestions for these transactions, and a note when the AI pass could not run (None when it did)."""
    cash_exists = cash.cash_account(create=False) is not None
    findings: list[Finding] = []
    unchecked: list[Transaction] = []
    for tx in transactions:
        found = _first_check(tx, cash_exists)
        if found is None and tx.type != "transfer":
            rule = category_rules.match(tx.description, tx.counterparty, tx.bank_description)
            if rule and rule != tx.category and rule in categories:
                found = Finding(tx, "category", rule, _("Categoria diversa dalle tue regole"),
                                _("La causale corrisponde alla categoria «%(category)s».", category=rule))
        if found:
            findings.append(found)
        elif tx.type != "transfer":
            unchecked.append(tx)

    note = None
    if unchecked and ai_classification.template_context()["ai_classifier"]:
        try:
            suggestions = ai_classification.classify(
                [{"id": tx.id, "text": tx.bank_description or tx.description, "amount": float(tx.signed_amount)}
                 for tx in unchecked[:AI_LIMIT]],
                categories)
        except AIExtractionError as exc:
            note = str(exc)
        else:
            by_id = {tx.id: tx for tx in unchecked}
            for tx_id, suggestion in suggestions.items():
                tx = by_id.get(tx_id)
                if tx is None or suggestion.category == tx.category or suggestion.category not in categories:
                    continue
                if suggestion.confidence not in ("alta", "media"):
                    continue
                findings.append(Finding(tx, "category", suggestion.category, _("Categoria che la causale suggerisce"),
                                        _("L'AI legge la causale come «%(category)s» (fiducia %(confidence)s).",
                                          category=tr(suggestion.category), confidence=suggestion.confidence)))
    return findings, note


def apply(tx: Transaction, kind: str, value: str) -> bool:
    """Make one suggested change. False when it does not apply (the transaction is left as it was)."""
    if kind == "type" and value in ("income", "expense", "transfer") and value != tx.type:
        tx.type = value
        if value != "transfer":
            tx.counter_account_id = None
        return True
    if kind == "category" and value:
        tx.category = value
        return True
    if kind == "cash":
        return cash.to_transfer(tx, cash.cash_account())
    return False
