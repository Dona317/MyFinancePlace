"""
The colours of income and expenses: two palettes that never mix, so every chart of income (pies, lines by category,
legends) speaks one family of colours and every chart of expenses the other, combined charts included. Each is
chosen in Impostazioni → Visualizzazione; the page gets them as CSS variables (--inc-1…8, --exp-1…8).
"""
from app.services.i18n import _l

# key → (name, eight colours that read well on light and dark backgrounds)
INCOME = {
    "verdi": (_l("Verdi e blu"), ["#12B886", "#15AABF", "#4C6EF5", "#40C057", "#22B8CF", "#748FFC", "#82C91E", "#0CA678"]),
    "blu":   (_l("Blu"),         ["#228BE6", "#4C6EF5", "#15AABF", "#7950F2", "#339AF0", "#5C7CFA", "#3BC9DB", "#845EF7"]),
    "verde": (_l("Verdi"),       ["#2F9E44", "#40C057", "#82C91E", "#12B886", "#69DB7C", "#94D82D", "#20C997", "#5C940D"]),
}
EXPENSE = {
    "caldi": (_l("Rossi, arancioni e rosa"), ["#FA5252", "#F76707", "#E64980", "#FAB005", "#FF8787", "#FD7E14", "#F06595", "#E8590C"]),
    "rossi": (_l("Rossi"),                   ["#E03131", "#FA5252", "#C92A2A", "#FF6B6B", "#F03E3E", "#FF8787", "#A61E4D", "#E64980"]),
    "viola": (_l("Viola e rosa"),            ["#7950F2", "#AE3EC9", "#E64980", "#9775FA", "#CC5DE8", "#F06595", "#5F3DC4", "#D6336C"]),
}
DEFAULT_INCOME, DEFAULT_EXPENSE = "verdi", "caldi"


def chosen(settings: dict) -> tuple[list[str], list[str]]:
    """The income and expense colours of these settings (the defaults for an unknown choice)."""
    income = INCOME.get(settings.get("palette_income"), INCOME[DEFAULT_INCOME])[1]
    expense = EXPENSE.get(settings.get("palette_expense"), EXPENSE[DEFAULT_EXPENSE])[1]
    return income, expense


def css_vars(settings: dict) -> str:
    """ "--inc-1:#…;…;--exp-8:#…" for the page's :root."""
    income, expense = chosen(settings)
    return ";".join([f"--inc-{i}:{c}" for i, c in enumerate(income, 1)] + [f"--exp-{i}:{c}" for i, c in enumerate(expense, 1)])
