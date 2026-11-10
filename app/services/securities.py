"""
Securities accounts, portfolios and the positions they hold (F42, decisions D8 and D9).

Every operation of a holding (trade, dividend, coupon, commission, tax) says in which securities account it sits and
to which portfolio it belongs. A position is one holding in one securities account for one portfolio: its units and
its cost come from the holding's opening position (when it sits there) and the trades of that pair, in date order,
with the weighted average cost of the position (a sale removes units at that average, D9).

The holding itself stays the instrument and the «Tutti» view: its quantity and average price are still computed over
all its trades by services.portfolio_ops, so nothing the app showed before F42 changes. The positions add the split
by securities account and by portfolio; their units always add up to the holding's.

An archive from before F42 (or a backup restored from then) gets its securities accounts and portfolio here: one
securities account for each account its trades moved money on, all in «Portafoglio principale» (ensure_assigned).
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal

from flask_babel import gettext as _

from app.extensions import db
from app.models.account import Account
from app.models.securities import Portfolio, SecuritiesAccount
from app.models.transaction import Transaction
from app.models.wealth import Holding
from app.services import money, tax_rules

DEFAULT_PORTFOLIO = "Portafoglio principale"
REGIMES = tax_rules.REGIMES


# ── Portfolios and securities accounts ─────────────────────────────────────────

def default_portfolio() -> Portfolio:
    """The portfolio trades go to when none is chosen (made the first time)."""
    found = Portfolio.query.filter_by(is_default=True).first()
    if found is None:
        found = Portfolio.query.filter_by(name=DEFAULT_PORTFOLIO).first()
        if found is None:
            found = Portfolio(name=DEFAULT_PORTFOLIO, position=0)
            db.session.add(found)
        found.is_default = True
        db.session.flush()
    return found


def portfolios(active_only: bool = True) -> list[Portfolio]:
    query = Portfolio.query.filter_by(active=True) if active_only else Portfolio.query
    return query.order_by(Portfolio.position, Portfolio.name).all()


def accounts(active_only: bool = True) -> list[SecuritiesAccount]:
    query = SecuritiesAccount.query.filter_by(active=True) if active_only else SecuritiesAccount.query
    return query.order_by(SecuritiesAccount.name).all()


def set_default(portfolio: Portfolio) -> None:
    """The star: exactly one default portfolio, where new operations go when none is chosen."""
    Portfolio.query.filter(Portfolio.is_default.is_(True)).update({"is_default": False}, synchronize_session=False)
    portfolio.is_default, portfolio.active = True, True


def save_portfolio(portfolio: Portfolio | None, name: str, description: str | None = None) -> Portfolio:
    """Create or rename a portfolio (names are unique, case aside)."""
    name = (name or "").strip()
    if not name:
        raise ValueError(_("Scrivi il nome del portafoglio."))
    clash = Portfolio.query.filter(db.func.lower(Portfolio.name) == name.lower()).first()
    if clash is not None and clash is not portfolio:
        raise ValueError(_("Esiste già un portafoglio «%(name)s».", name=name))
    if portfolio is None:
        last = db.session.query(db.func.max(Portfolio.position)).scalar() or 0
        portfolio = Portfolio(position=last + 1)
        db.session.add(portfolio)
    portfolio.name, portfolio.description = name, (description or "").strip() or None
    db.session.flush()
    if Portfolio.query.filter_by(is_default=True).first() is None:
        set_default(portfolio)
    return portfolio


def operations_count(portfolio: Portfolio | None = None, securities_account: SecuritiesAccount | None = None) -> int:
    query = Transaction.query
    if portfolio is not None:
        query = query.filter(Transaction.portfolio_id == portfolio.id)
    if securities_account is not None:
        query = query.filter(Transaction.securities_account_id == securities_account.id)
    return query.count()


def delete_portfolio(portfolio: Portfolio) -> None:
    """Only an empty portfolio that is not the default one goes; one with operations is archived instead."""
    if portfolio.is_default:
        raise ValueError(_("Il portafoglio predefinito non si elimina: metti prima la stella su un altro."))
    used = operations_count(portfolio) or Holding.query.filter_by(opening_portfolio_id=portfolio.id).count()
    if used:
        portfolio.active = False
    else:
        db.session.delete(portfolio)


def save_account(dossier: SecuritiesAccount | None, data: dict) -> SecuritiesAccount:
    """Create or change a securities account. It always has a settlement account: its liquidity."""
    name = (data.get("name") or "").strip()
    if not name:
        raise ValueError(_("Scrivi il nome del conto titoli."))
    clash = SecuritiesAccount.query.filter(db.func.lower(SecuritiesAccount.name) == name.lower()).first()
    if clash is not None and clash is not dossier:
        raise ValueError(_("Esiste già un conto titoli «%(name)s».", name=name))
    settlement = db.session.get(Account, data.get("settlement_account_id") or 0)
    if settlement is None:
        raise ValueError(_("Scegli il conto di liquidità del conto titoli: ogni conto titoli ne ha uno."))
    if dossier is None:
        dossier = SecuritiesAccount()
        db.session.add(dossier)
    dossier.name, dossier.settlement_account_id = name, settlement.id
    dossier.broker = (data.get("broker") or "").strip() or settlement.bank or settlement.name
    dossier.tax_regime = data.get("tax_regime") if data.get("tax_regime") in REGIMES else "amministrato"
    dossier.abroad = bool(data.get("abroad"))
    for field in ("fee_fixed", "fee_percent", "fee_min", "fee_max"):
        setattr(dossier, field, data.get(field))
    dossier.notes = (data.get("notes") or "").strip() or None
    dossier.active = bool(data.get("active", True))
    db.session.flush()
    return dossier


def cash(dossier: SecuritiesAccount, on=None) -> float:
    """The liquidity of a securities account: the balance of its settlement account."""
    from app.services import accounts

    account = dossier.settlement_account
    return accounts.balance(account, on) if account is not None else 0.0


def _unique_name(base: str) -> str:
    name, number = base, 2
    while SecuritiesAccount.query.filter_by(name=name).first() is not None:
        name, number = f"{base} {number}", number + 1
    return name


def for_settlement(account: Account) -> SecuritiesAccount:
    """The securities account whose money moves on this account: the first one found, or a new one with the
    account's commission rules and tax regime («Titoli Directa» for «Directa»)."""
    found = (SecuritiesAccount.query.filter_by(settlement_account_id=account.id)
             .order_by(SecuritiesAccount.active.desc(), SecuritiesAccount.id).first())
    if found is None:
        found = SecuritiesAccount(name=_unique_name(f"Titoli {account.name}"), broker=account.bank or account.name,
                                  settlement_account_id=account.id, owner=account.owner,
                                  tax_regime=account.tax_regime or "amministrato", abroad=bool(account.abroad),
                                  fee_fixed=account.fee_fixed, fee_percent=account.fee_percent,
                                  fee_min=account.fee_min, fee_max=account.fee_max)
        db.session.add(found)
        db.session.flush()
    return found


def _money_account_id(tx: Transaction) -> int | None:
    """The account the money of an operation moves on: where a purchase is paid from, where a sale is paid to."""
    return tx.account_id if tx.account_id is not None else tx.counter_account_id


def assign(created: list[Transaction], securities_account: SecuritiesAccount | None,
           portfolio: Portfolio | None) -> None:
    """Mark the transactions of one operation (the trade and its commission, or the income) with their place."""
    portfolio = portfolio or default_portfolio()
    for tx in created:
        tx.securities_account_id = securities_account.id if securities_account else None
        tx.portfolio_id = portfolio.id


def ensure_assigned() -> int:
    """Give the operations recorded before F42 (or restored from an older backup) their securities account and
    portfolio, and the opening positions their portfolio; how many rows changed. Nothing already set is touched."""
    changed = 0
    portfolio = default_portfolio()
    linked = (Transaction.query.filter(Transaction.holding_id.isnot(None))
              .filter((Transaction.portfolio_id.is_(None)) | (Transaction.securities_account_id.is_(None))).all())
    cache: dict[int, SecuritiesAccount] = {}
    for tx in linked:
        if tx.portfolio_id is None:
            tx.portfolio_id = portfolio.id
            changed += 1
        account_id = _money_account_id(tx)
        if tx.securities_account_id is None and account_id is not None:
            if account_id not in cache:
                account = db.session.get(Account, account_id)
                cache[account_id] = for_settlement(account) if account is not None else None
            if cache[account_id] is not None:
                tx.securities_account_id = cache[account_id].id
                changed += 1
    db.session.flush()
    # a commission belongs where its trade is
    fees = Transaction.query.filter(Transaction.fee_for_id.isnot(None),
                                    (Transaction.portfolio_id.is_(None)) | (Transaction.securities_account_id.is_(None)))
    for fee in fees:
        trade = fee.fee_for
        if trade is None:
            continue
        if fee.portfolio_id is None and trade.portfolio_id is not None:
            fee.portfolio_id, changed = trade.portfolio_id, changed + 1
        if fee.securities_account_id is None and trade.securities_account_id is not None:
            fee.securities_account_id, changed = trade.securities_account_id, changed + 1
    for holding in Holding.query.filter(Holding.opening_portfolio_id.is_(None), Holding.opening_quantity > 0):
        holding.opening_portfolio_id = portfolio.id
        if holding.opening_account_id is None:
            first = (Transaction.query.filter(Transaction.holding_id == holding.id,
                                              Transaction.securities_account_id.isnot(None))
                     .order_by(Transaction.date, Transaction.id).first())
            holding.opening_account_id = first.securities_account_id if first else None
        changed += 1
    db.session.flush()
    return changed


# ── Positions ──────────────────────────────────────────────────────────────────

@dataclass
class Position:
    """One holding in one securities account for one portfolio. It reads like a holding (name, quantity, average
    price, value, gain…), so the portfolio's tables and summary show positions and holdings alike."""
    holding: Holding
    securities_account_id: int | None
    portfolio_id: int | None
    quantity: Decimal = Decimal(0)
    cost_basis: Decimal = Decimal(0)  # what the units still held cost, commissions of the purchases included

    def __getattr__(self, name):  # id, name, ticker, asset_class, price, price_date…: the holding's
        if name.startswith("_") or name == "holding":
            raise AttributeError(name)
        return getattr(self.holding, name)

    @property
    def avg_price(self) -> Decimal:
        return money.price(self.cost_basis / self.quantity) if self.quantity > 0 else Decimal(0)

    @property
    def _multiplier(self) -> float:
        return float(self.holding.multiplier if self.holding.multiplier is not None else 1)

    @property
    def units(self) -> float:
        return float(self.quantity) * self._multiplier

    @property
    def cost(self) -> float:
        return float(self.cost_basis) * self._multiplier

    @property
    def value(self) -> float:
        return self.units * self.holding.price

    @property
    def gain(self) -> float:
        return self.value - self.cost

    @property
    def gain_pct(self) -> float:
        return self.gain / self.cost * 100 if self.cost else 0.0


def positions(holdings: list[Holding] | None = None, portfolio_id: int | None = None,
              securities_account_id: int | None = None, include_closed: bool = False) -> list[Position]:
    """The positions of the holdings (all when None), optionally of one portfolio and/or one securities account;
    a position whose units went back to zero only with include_closed."""
    holdings = holdings if holdings is not None else Holding.query.all()
    by_id = {h.id: h for h in holdings}
    found: dict[tuple, Position] = {}

    def slot(holding: Holding, account_id, folio_id) -> Position:
        key = (holding.id, account_id, folio_id)
        if key not in found:
            found[key] = Position(holding, account_id, folio_id)
        return found[key]

    default_id = default_portfolio().id
    for holding in holdings:
        quantity = Decimal(holding.opening_quantity or 0)
        if quantity > 0:
            price = holding.opening_price if holding.opening_price is not None else holding.avg_price
            position = slot(holding, holding.opening_account_id, holding.opening_portfolio_id or default_id)
            position.quantity += quantity
            position.cost_basis += quantity * Decimal(price or 0)
    if by_id:
        trades = (Transaction.query.filter(Transaction.holding_id.in_(list(by_id)), Transaction.units.isnot(None),
                                           Transaction.unit_price.isnot(None))
                  .order_by(Transaction.date, Transaction.id).all())
        fees = defaultdict(Decimal)
        rows = (db.session.query(Transaction.fee_for_id, db.func.sum(Transaction.amount))
                .filter(Transaction.fee_for_id.in_([t.id for t in trades] or [0])).group_by(Transaction.fee_for_id))
        for trade_id, total in rows:
            fees[trade_id] = Decimal(total)
        for trade in trades:
            position = slot(by_id[trade.holding_id], trade.securities_account_id, trade.portfolio_id or default_id)
            units, price = Decimal(trade.units), Decimal(trade.unit_price)
            if units > 0:
                position.cost_basis += units * price + fees[trade.id]
                position.quantity += units
            elif position.quantity > 0:
                sold = min(-units, position.quantity)
                position.cost_basis -= position.cost_basis / position.quantity * sold
                position.quantity -= sold
            else:  # sold from a position that holds nothing here: kept visible, so the mismatch can be fixed
                position.quantity += units
    out = [p for p in found.values()
           if (portfolio_id is None or p.portfolio_id == portfolio_id)
           and (securities_account_id is None or p.securities_account_id == securities_account_id)
           and (include_closed or p.quantity != 0)]
    return sorted(out, key=lambda p: (p.holding.name.lower(), p.securities_account_id or 0, p.portfolio_id or 0))


def main_place(holding: Holding) -> SecuritiesAccount | None:
    """Where a new purchase of a holding goes when nothing is chosen: the securities account that already holds most
    of it, or the only active one."""
    held = [p for p in positions([holding]) if p.quantity > 0 and p.securities_account_id]
    if held:
        return db.session.get(SecuritiesAccount, max(held, key=lambda p: p.quantity).securities_account_id)
    active = accounts()
    return active[0] if len(active) == 1 else None


def holdings_in(portfolio_id: int | None = None, securities_account_id: int | None = None) -> list[Holding]:
    """The holdings with units in a portfolio and/or a securities account."""
    seen: dict[int, Holding] = {}
    for position in positions(portfolio_id=portfolio_id, securities_account_id=securities_account_id):
        seen.setdefault(position.holding.id, position.holding)
    return list(seen.values())
