"""
The merchant or payee named in a bank causale, without any model: "Pagamento carta - PAGAMENTO POS ESSELUNGA
MILANO" → "Esselunga", "Bonifico a IMMOBILIARE CASA BELLA SRL per AFFITTO 07/2026" → "Immobiliare Casa Bella",
"Addebito SDD - ENEL ENERGIA SPA bolletta luce 07/2026" → "Enel Energia", "NETFLIX.COM AMSTERDAM" → "Netflix".

It becomes the transaction's counterparty (its first tag). None when the causale names nobody (bank fees,
transfers between own accounts, cash withdrawals).
"""
from __future__ import annotations

import re

# What banks write before the merchant, in any case, possibly repeated ("Pagamento carta - PAGAMENTO POS …")
PREFIXES = [
    "pagamento carta", "pagamento pos", "pagamento tramite pos", "pagamento visa debit presso", "pagamento visa presso",
    "pagamento mastercard presso", "pagamento contactless", "pagamento", "pagam pos", "pag pos", "pos",
    "addebito sdd", "addebito diretto", "addebito", "sdd", "bonifico sepa", "bonifico istantaneo", "card payment",
    "acquisto", "operazione", "presso",
]
_PREFIX = re.compile(r"^(?:(?:" + "|".join(re.escape(p) for p in sorted(PREFIXES, key=len, reverse=True))
                     + r")\b[\s:\-–]*)+", re.IGNORECASE)
# A transfer names its counterpart between "a/da/verso/a favore di" and "per"/"causale"
_TRANSFER = re.compile(r"^(?:bonifico|giroconto|payment|transfer)?\s*(?:a favore di|verso|from|to|da|a)\s+(.+?)"
                       r"(?:\s+(?:per|causale|rif|ref|for)\b.*)?$", re.IGNORECASE)
NOBODY = re.compile(r"\b(commission[ei]|canone|imposta di bollo|bollo|interessi|giroconto|prelievo|bancomat atm|"
                    r"atm withdrawal|cash withdrawal|competenze|spese tenuta)\b", re.IGNORECASE)
LEGAL = re.compile(r"\b(s\.?p\.?a\.?|s\.?r\.?l\.?s?|s\.?a\.?s\.?|s\.?n\.?c\.?|sarl|gmbh|ltd|limited|inc|llc|ab|bv|nv|"
                   r"s\.?a\.?|plc)\b\.?", re.IGNORECASE)
PLACES = {
    "milano", "roma", "torino", "napoli", "bologna", "firenze", "genova", "venezia", "verona", "padova", "bari",
    "palermo", "catania", "brescia", "bergamo", "monza", "italia", "italy", "it", "eu", "europe", "amsterdam",
    "stockholm", "dublin", "dublino", "luxembourg", "lussemburgo", "london", "londra", "paris", "parigi", "berlin",
    "madrid", "barcelona", "ie", "lu", "nl", "se", "gb", "uk", "fr", "de", "es", "us",
}
# Kinds of shop: alone they name nothing, so a place after them is part of the name
GENERIC = {"pizzeria", "bar", "ristorante", "trattoria", "osteria", "farmacia", "hotel", "albergo", "cafe", "caffe",
           "caffè", "panificio", "pasticceria", "gelateria", "supermercato", "tabacchi", "edicola", "parcheggio"}
STREET = re.compile(r"\b(via|viale|corso|piazza|p\.?za|largo|strada|vicolo|str)\b.*$", re.IGNORECASE)
TAIL = re.compile(r"(\s+(\d{1,2}[/.-]\d{1,2}([/.-]\d{2,4})?|\d{1,2}[/.-]\d{4}|\d+|n\.?\s*\d+|\*+\d*|#\d+))+$")
DOMAIN = re.compile(r"\.(com|it|eu|net|org|co\.uk|de|fr)\b", re.IGNORECASE)
CODE = re.compile(r"^(?=.*[A-Z])(?=.*[\d&])[A-Z0-9&]+$")  # Q8, A2A, H&M: kept as written
SMALL = {"da", "di", "del", "della", "dei", "e", "la", "il", "lo", "le", "of", "the", "and", "de"}


def _pretty(name: str) -> str:
    """ "RISTORANTE DA LUIGI" → "Ristorante da Luigi"; codes (Q8, A2A) and a lone short name (ATM) stay as they are."""
    words = name.split()
    if len(words) == 1 and len(name) <= 3 and name.isupper():
        return name
    pretty = []
    for i, word in enumerate(words):
        if CODE.match(word):
            pretty.append(word)
        elif i and word.lower() in SMALL:
            pretty.append(word.lower())
        else:
            pretty.append(word[:1].upper() + word[1:].lower())
    return " ".join(pretty)


def _cut_lowercase_tail(text: str) -> str:
    """ "A2A ENERGIA gas" → "A2A ENERGIA": banks write the name in capitals and what it is for in lower case."""
    words = text.split()
    for i, word in enumerate(words):
        if i and word.islower() and any(w.isupper() for w in words[:i]):
            return " ".join(words[:i])
    return text


def extract(description: str | None, details: str | None = None) -> str | None:
    """The merchant or payee named in the causale (`description`, else `details`); None when there is none."""
    for text in (description, details):
        name = _from(text)
        if name:
            return name
    return None


def _from(text: str | None) -> str | None:
    text = " ".join((text or "").split())
    if not text or NOBODY.search(text):
        return None
    text = _PREFIX.sub("", text)
    if " - " in text:  # "Bonifico SEPA - Bonifico a …", "Pagamento carta - …": the part after the bank's label
        text = _PREFIX.sub("", text.split(" - ", 1)[1]) or text
    transfer = _TRANSFER.match(text)
    if transfer and re.match(r"^(bonifico|payment|transfer|da|a|verso|from|to|a favore)\b", text, re.IGNORECASE):
        text = transfer.group(1)
    # after a company form comes what was bought ("ENEL ENERGIA SPA bolletta luce"): stop there
    legal = LEGAL.search(text)
    if legal and legal.start() > 0:
        text = text[:legal.start()]
    text = _cut_lowercase_tail(text)
    text = DOMAIN.sub("", text)
    text = STREET.sub("", text)
    text = LEGAL.sub("", text)
    words = text.split()
    while len(words) > 1 and (words[-1].lower().strip(".,") in PLACES or TAIL.fullmatch(" " + words[-1])):
        if words[-1].lower().strip(".,") in PLACES and len(words) == 2 and words[0].lower() in GENERIC:
            break  # "PIZZERIA NAPOLI" is the name, not a pizzeria in Naples
        words.pop()
    text = TAIL.sub("", " ".join(words)).strip(" -–:,.*")
    if len(text) < 2 or not re.search(r"[A-Za-z]", text):
        return None
    return _pretty(text)
