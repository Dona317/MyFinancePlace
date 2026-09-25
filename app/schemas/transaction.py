from apiflask import Schema
from apiflask.fields import Boolean, String, Integer, Float, Date, List, Nested
from apiflask.validators import OneOf, Range, Length

TRANSACTION_TYPES = ["income", "expense", "transfer"]
RECURRENCES       = ["weekly", "monthly", "quarterly", "yearly"]


class TransactionIn(Schema):
    description     = String(required=True,  validate=Length(min=1, max=255), metadata={"example": "Grocery shopping"})
    amount          = Float(required=True,   validate=Range(min=0.01), metadata={"example": 49.99})
    currency        = String(load_default="EUR", validate=Length(equal=3), metadata={"example": "EUR"})
    date            = Date(required=True,    metadata={"example": "2026-06-15"})
    type            = String(required=True,  validate=OneOf(TRANSACTION_TYPES), metadata={"example": "expense"})
    category        = String(load_default=None, allow_none=True, metadata={"example": "Alimentari"})
    counterparty    = String(load_default=None, allow_none=True, metadata={"example": "Esselunga"})
    tags            = List(String(), load_default=list, metadata={"example": ["cibo", "casa"]})
    is_recurring    = Boolean(load_default=False)
    recurrence      = String(load_default=None, allow_none=True, validate=OneOf(RECURRENCES))
    recurrence_end  = Date(load_default=None, allow_none=True)
    notes           = String(load_default=None, allow_none=True)


class TransactionOut(Schema):
    id              = Integer()
    description     = String()
    amount          = Float()
    currency        = String()
    date            = Date()
    type            = String()
    category        = String()
    counterparty    = String()
    tags            = List(String())
    is_recurring    = Boolean()
    recurrence      = String()
    recurrence_end  = Date()
    notes           = String()


class TransactionListOut(Schema):
    success      = Boolean()
    transactions = List(Nested(TransactionOut))
    total        = Integer()
