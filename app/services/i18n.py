"""
Interface language helpers. Italian is the source language; English lives in app/translations.

- `_l` (lazy_gettext) for labels defined at import time and only shown (methods, frequencies, kinds).
- `N_` marks words that are also stored as data (policy types, debt types, asset classes, document types):
  the database keeps the Italian value, `tr()` (the `|tr` template filter) shows it in the chosen language.
"""
from flask_babel import gettext  # noqa: F401 - re-exported
from flask_babel import lazy_gettext as _l  # noqa: F401 - re-exported


def N_(text: str) -> str:
    """Mark a stored word for translation without translating it (extracted with `pybabel -k N_`)."""
    return text


def tr(value):
    """A stored word (or any known label) in the interface language; anything else unchanged."""
    return gettext(value) if isinstance(value, str) and value else value
