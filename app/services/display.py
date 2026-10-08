"""
How numbers, amounts and dates are shown, from the preferences in Settings → Visualizzazione:
base currency (symbol of every total), number format (1.234,56 or 1,234.56) and date format.
"""
from datetime import date, datetime

from app.services import request_cache

LOCALES = {  # code: (label, thousands separator, decimal separator)
    "it-IT": ("Italiano — 1.234,56", ".", ","),
    "en-GB": ("Inglese — 1,234.56", ",", "."),
    "de-CH": ("Svizzero — 1'234.56", "'", "."),
}
DATE_FORMATS = {"DD/MM/YYYY": "%d/%m/%Y", "YYYY-MM-DD": "%Y-%m-%d", "MM/DD/YYYY": "%m/%d/%Y"}


def prefs() -> dict:
    store = request_cache.cache()
    if "display" not in store:
        from app.services.ui_settings import current_settings
        from app.services import currency

        settings = current_settings()
        locale = settings.get("locale") if settings.get("locale") in LOCALES else "it-IT"
        store["display"] = {
            "currency": currency.base(),
            "symbol": currency.symbol(currency.base()),
            "locale": locale,
            "date_format": DATE_FORMATS.get(settings.get("date_format"), "%d/%m/%Y"),
        }
    return store["display"]


def number(value, decimals: int = 2, trim: bool = False) -> str:
    _, thousands, decimal = LOCALES[prefs()["locale"]]
    text = f"{abs(float(value or 0)):,.{decimals}f}"
    whole, _, fraction = text.partition(".")
    if trim:
        fraction = fraction.rstrip("0")
    text = whole.replace(",", thousands) + (decimal + fraction if fraction else "")
    return ("-" if float(value or 0) < 0 else "") + text


def money(value, symbol: str | None = None) -> str:
    formatted = number(abs(float(value or 0)))
    sign = "-" if float(value or 0) < 0 else ""
    return f"{sign}{symbol or prefs()['symbol']} {formatted}"


def day(value) -> str:
    if not value:
        return "—"
    if isinstance(value, datetime):
        value = value.date()
    return value.strftime(prefs()["date_format"]) if isinstance(value, date) else str(value)
