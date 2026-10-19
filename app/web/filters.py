"""Jinja filters: amounts, numbers and dates follow Settings → Visualizzazione (services.display)."""
from flask import Flask

from app.services import categories, display, i18n

TONES = {"expense": "negative", "income": "positive"}


def filesize(size) -> str:
    size = float(size or 0)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}".replace(".", ",")
        size /= 1024
    return ""  # not reached


def register_filters(app: Flask) -> None:
    filters = {
        "money": display.money,                                        # 1234.5 → '€ 1.234,50'
        "number": lambda value, decimals=2: display.number(value, decimals, trim=True),  # 1234.5 → '1.234,5'
        "plain": display.plain,                                        # a stored number as a form value: '10,5'
        "filesize": filesize,
        "category_label": categories.label,                            # 'Bollette › Luce'
        "category_top": categories.top,
        "tr": i18n.tr,                                                 # a word stored in Italian, translated
        "it_date": display.day,
        "tone": lambda tx_type: TONES.get(tx_type, ""),                # red expenses, green income
    }
    for name, function in filters.items():
        app.add_template_filter(function, name)
    app.jinja_env.globals["category_groups"] = categories.grouped
