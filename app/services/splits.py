"""Split transactions: one amount divided across several categories (100 € = 70 Spesa + 30 Casa)."""
from decimal import Decimal

from app.models.transaction import Transaction, TransactionSplit
from app.services import display
from flask_babel import gettext as _


def apply(tx: Transaction, parts: list[tuple[str | None, Decimal | None]]) -> None:
    """
    Set the parts of `tx` (after its amount and type): ≥ 2 parts, each with a category and a positive amount, adding
    up to the amount. Fewer than 2 parts: an ordinary transaction. `category` becomes the largest part's, so lists
    and filters keep working. A ValueError says what is wrong.
    """
    if len(parts) < 2:
        tx.splits = []
        return
    if tx.type == "transfer":
        raise ValueError(_("Suddivisione: un trasferimento tra conti non si suddivide in categorie."))
    for number, (category, amount) in enumerate(parts, start=1):
        if not category:
            raise ValueError(_("Suddivisione, riga %(n)s: scegli una categoria.", n=number))
        if amount is None or amount <= 0:
            raise ValueError(_("Suddivisione, riga %(n)s: l'importo deve essere positivo.", n=number))
    total = sum(amount for _category, amount in parts)
    if total != abs(Decimal(tx.amount)):
        raise ValueError(_("Suddivisione: le parti fanno %(parts)s ma l'importo è %(total)s.",
                           parts=display.number(total), total=display.number(abs(tx.amount))))
    tx.splits = [TransactionSplit(category=category, amount=amount) for category, amount in parts]
    tx.category = max(parts, key=lambda part: part[1])[0]
