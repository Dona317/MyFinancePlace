"""Automatic category of a statement row: the user's rules, the history, the built-in keywords."""
from __future__ import annotations

import re

from app.services import categories, category_rules, history_classifier
from app.services.parsing import normalize

# ── Auto-categorization ────────────────────────────────────────────────────────

# First match wins; keywords are matched as whole words, case-insensitive.
CATEGORY_RULES: list[tuple[str, tuple[str, ...]]] = [
    ("Stipendio",    ("stipendio", "emolumenti", "retribuzione", "salario", "busta paga", "cedolino")),
    ("Alimentari",   ("esselunga", "coop", "conad", "carrefour", "lidl", "eurospin", "pam", "penny", "aldi",
                      "supermercato", "supermercati", "iper", "despar", "famila", "bennet", "naturasi",
                      "alimentari", "spesa")),
    ("Trasporto",    ("eni", "enilive", "q8", "tamoil", "esso", "shell", "carburante", "carburanti", "benzina",
                      "trenitalia", "italo", "atm", "atac", "autostrade", "telepass", "uber", "taxi", "freenow",
                      "ryanair", "easyjet", "ita airways", "flixbus",
                      "parcheggio", "trasporti")),
    ("Abbonamenti",  ("netflix", "spotify", "prime video", "amazon prime", "disney", "dazn", "now tv", "icloud",
                      "apple com bill", "youtube", "tim", "vodafone", "windtre", "iliad", "fastweb", "ho mobile",
                      "abbonamento", "abbonamenti")),
    ("Casa",         ("affitto", "condominio", "enel", "a2a", "hera", "iren", "edison", "sorgenia", "bolletta",
                      "tari", "ikea", "leroy merlin", "casa", "utenze")),
    ("Salute",       ("farmacia", "ospedale", "medico", "dentista", "asl", "ticket", "sanitaria", "salute")),
    ("Svago",        ("ristorante", "pizzeria", "trattoria", "bar", "cinema", "just eat", "deliveroo", "glovo",
                      "mcdonald", "burger king", "starbucks", "booking com", "airbnb", "svago", "tempo libero", "viaggi")),
    ("Investimenti", ("compravendita titoli", "acquisto titoli", "etf", "fondi", "pac", "dossier titoli",
                      "investimenti")),
    ("Commissioni",  ("commissioni", "commissione", "canone", "imposta di bollo", "spese tenuta conto",
                      "competenze")),
    ("Rimborsi",     ("rimborso", "storno")),
]

TRANSFER_KEYWORDS = ("giroconto", "trasferimento tra conti", "ricarica carta", "girofondi")

_RULE_PATTERNS = [
    (category, re.compile(r"\b(" + "|".join(re.escape(k) for k in keywords) + r")\b"))
    for category, keywords in CATEGORY_RULES
]
_TRANSFER_PATTERN = re.compile(r"\b(" + "|".join(re.escape(k) for k in TRANSFER_KEYWORDS) + r")\b")


def search_text(*parts: str | None) -> str:
    """Normalized text padded with spaces, so keywords can be matched as whole words."""
    return f" {normalize(' '.join(p for p in parts if p))} "


def categorize(description: str, details: str | None = None, bank_category: str | None = None,
               income: bool | None = None, history=None) -> str:
    """App category for a statement row: the user's rules, what the user's history says (when the direction is
    known), the built-in keyword rules, the bank's category, "Altro"."""
    learned = category_rules.match(description, details)
    if learned:
        return learned
    if income is not None:
        guessed = history_classifier.guess(" ".join(filter(None, (description, details))), income, history)
        if guessed:
            return guessed.category
    text = search_text(description, details)
    for category, pattern in _RULE_PATTERNS:
        if pattern.search(text):
            return category
    if bank_category:
        bank_text = search_text(bank_category)
        for category, pattern in _RULE_PATTERNS:
            if pattern.search(bank_text):
                return category
        return bank_category.strip()
    return categories.FALLBACK


def is_transfer(description: str, details: str | None = None) -> bool:
    return bool(_TRANSFER_PATTERN.search(search_text(description, details)))
