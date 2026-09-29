"""
Downloadable PDF of the yearly financial report, generated on the server with fpdf2 (pure Python, no
system libraries). Same content as the printable page export/report.html: key figures, income statement
by category, monthly table and cash flow.
"""
from datetime import datetime

from fpdf import FPDF
from fpdf.fonts import FontFace

INK = (26, 37, 64)
MUTED = (107, 122, 153)
LINE = (221, 227, 238)
SECTION_BG = (244, 246, 250)


def money(value, symbol: str = "€") -> str:
    """Italian format, same as the `money` template filter: -1234.5 → '-€ 1.234,50'."""
    number = float(value or 0)
    formatted = f"{abs(number):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{'-' if number < 0 else ''}{symbol} {formatted}"


def percent(value) -> str:
    return "—" if value is None else f"{float(value):.1f}%".replace(".", ",")


class _ReportPDF(FPDF):
    def __init__(self, title: str):
        super().__init__(format="A4")
        self.core_fonts_encoding = "windows-1252"   # €, curly quotes and dashes with the built-in fonts
        self.report_title = title
        self.set_margins(15, 15, 15)
        self.set_auto_page_break(True, margin=18)
        self.set_title(title)
        self.set_author("MyFinancePlace")
        self.set_creator("MyFinancePlace")

    def footer(self):
        self.set_y(-12)
        self.set_font("Helvetica", size=8)
        self.set_text_color(*MUTED)
        self.cell(0, 5, f"{self.report_title} · pagina {self.page_no()}/{{nb}}", align="C")


def _heading(pdf: FPDF, text: str):
    pdf.ln(6)
    pdf.set_font("Helvetica", "B", 12)
    pdf.set_text_color(*INK)
    pdf.cell(0, 7, text, new_x="LMARGIN", new_y="NEXT")
    pdf.set_draw_color(*INK)
    pdf.set_line_width(0.5)
    pdf.line(pdf.l_margin, pdf.get_y(), pdf.w - pdf.r_margin, pdf.get_y())
    pdf.ln(2)


def _kpis(pdf: FPDF, items: list[tuple[str, str]]):
    gap = 4
    width = (pdf.epw - gap * (len(items) - 1)) / len(items)
    top = pdf.get_y()
    pdf.set_draw_color(*LINE)
    pdf.set_line_width(0.3)
    for index, (label, value) in enumerate(items):
        x = pdf.l_margin + index * (width + gap)
        pdf.rect(x, top, width, 18, round_corners=True, style="D")
        pdf.set_xy(x + 3, top + 3)
        pdf.set_font("Helvetica", size=7)
        pdf.set_text_color(*MUTED)
        pdf.cell(width - 6, 4, label.upper())
        pdf.set_xy(x + 3, top + 9)
        pdf.set_font("Helvetica", "B", 11)
        pdf.set_text_color(*INK)
        pdf.cell(width - 6, 6, value)
    pdf.set_y(top + 22)


def _table(pdf: FPDF, header: list[str] | None, rows: list[tuple], widths: tuple, styles: dict | None = None):
    """rows: tuples of cells; `styles` maps a row index to "section" or "total"."""
    styles = styles or {}
    pdf.set_font("Helvetica", size=9)
    pdf.set_text_color(*INK)
    pdf.set_draw_color(*LINE)
    pdf.set_line_width(0.2)
    align = ["LEFT"] + ["RIGHT"] * (len(widths) - 1)
    with pdf.table(
        col_widths=widths, text_align=align, borders_layout="HORIZONTAL_LINES", line_height=6,
        first_row_as_headings=bool(header),
        headings_style=FontFace(emphasis="BOLD", color=MUTED, size_pt=8),
        padding=(1, 2),
    ) as table:
        if header:
            table.row(header)
        for index, cells in enumerate(rows):
            kind = styles.get(index)
            if kind == "section":
                row = table.row(style=FontFace(emphasis="BOLD", size_pt=8, fill_color=SECTION_BG))
                row.cell(cells[0], colspan=len(widths), align="LEFT")
            else:
                style = FontFace(emphasis="BOLD") if kind == "total" else None
                table.row(list(cells), style=style)


def build_report(year: int, statement: dict, cash_flow: dict, generated_at: datetime | None = None) -> bytes:
    """The report as PDF bytes; `statement` and `cash_flow` come from analytics.income_statement / cash_flow."""
    generated_at = generated_at or datetime.now()
    title = f"Report Finanziario {year}"
    pdf = _ReportPDF(title)
    pdf.add_page()

    pdf.set_font("Helvetica", "B", 18)
    pdf.set_text_color(*INK)
    pdf.cell(0, 9, title, new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", size=9)
    pdf.set_text_color(*MUTED)
    pdf.cell(0, 5, f"MyFinancePlace · generato il {generated_at:%d/%m/%Y %H:%M}", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(5)

    summary = statement["summary"]
    _kpis(pdf, [
        ("Entrate", money(summary["income"])),
        ("Uscite", money(summary["expenses"])),
        ("Risparmio netto", money(summary["net"])),
        ("Tasso di risparmio", percent(summary["savings_rate"])),
    ])

    _heading(pdf, "Conto Economico")
    rows, styles = [], {}

    def section(label: str, lines: list[dict], empty: str):
        styles[len(rows)] = "section"
        rows.append((label,))
        for line in lines or [{"category": empty, "amount": None, "share_of_income": None}]:
            amount = "" if line["amount"] is None else money(line["amount"])
            share = "" if line["amount"] is None else percent(line["share_of_income"])
            rows.append((line["category"] or "—", amount, share))

    section("Entrate", statement["income_lines"], "Nessuna entrata")
    section("Uscite", statement["expense_lines"], "Nessuna uscita")
    styles[len(rows)] = "total"
    rows.append(("Risparmio netto", money(summary["net"]), percent(summary["savings_rate"]) if summary["income"] else "—"))
    _table(pdf, ["Voce", "Importo", "% Entrate"], rows, (100, 45, 35), styles)

    _heading(pdf, "Andamento Mensile")
    monthly = statement["monthly"]
    rows = [
        (label, money(monthly["income"][i]), money(monthly["expenses"][i]), money(monthly["net"][i]))
        for i, label in enumerate(monthly["labels"])
    ]
    _table(pdf, ["Mese", "Entrate", "Uscite", "Netto"], rows, (45, 45, 45, 45))

    _heading(pdf, "Rendiconto Finanziario")
    rows = [
        ("A — Flusso operativo", money(cash_flow["operating"])),
        ("B — Flusso di investimento", money(cash_flow["investing"])),
        ("C — Flusso finanziario", money(cash_flow["financing"])),
        ("Variazione netta cassa (A+B+C)", money(cash_flow["net_change"])),
    ]
    _table(pdf, None, rows, (135, 45), {3: "total"})

    return bytes(pdf.output())
