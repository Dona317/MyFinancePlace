# Importing the models registers them with SQLAlchemy (tables, migrations).
from .account import Account
from .budget import Budget
from .category import Category, CategoryRule
from .client import Client, ClientGroup
from .currency import ExchangeRate
from .duplicate import DuplicateDismissal
from .event import SpendingEvent
from .gig import Gig
from .limit import ContributionLimit
from .personal_loan import PersonalLoan
from .portfolio_model import InvestmentPlan, PortfolioRule, PortfolioTemplate, SlotHolding, TemplateSlot
from .setting import AppSetting
from .taxonomy import HoldingCategory, Taxonomy, TaxonomyCategory
from .transaction import Transaction, TransactionSplit
from .user import User
from .wealth import Debt, Document, Goal, Holding, HoldingPrice, InsurancePolicy, Snapshot

__all__ = [
    "Account", "Transaction", "TransactionSplit", "AppSetting", "DuplicateDismissal", "Category", "CategoryRule",
    "ExchangeRate", "Budget", "User", "Client", "ClientGroup", "Holding", "HoldingPrice", "Debt", "InsurancePolicy", "Goal", "Document", "Snapshot",
    "PortfolioTemplate", "TemplateSlot", "SlotHolding", "PortfolioRule", "InvestmentPlan", "SpendingEvent",
    "ContributionLimit", "Taxonomy", "TaxonomyCategory", "HoldingCategory", "Gig", "PersonalLoan",
]
