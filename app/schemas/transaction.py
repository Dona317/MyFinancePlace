from apiflask import Schema
from apiflask.fields import Boolean, String, Integer, Float, Date, List, Nested
from apiflask.validators import OneOf, Range


class TransactionIn(Schema):
    descripotion    = String(required=True,  metadata={"example": "Grocery shopping"})
    amount          = Float(required=True,   validate=Range(min=0.01), metadata={"example": 49.99})
    date            = Date(required=True,    metadata={"example": "2026-06-15"})
    category        = String(required=True,  metadata={"example": "Food"})
    type            = String(required=True,  validate=OneOf(["income", "expense"]), metadata={"example": "expense"})
    notes           = String(load_default="")


class TransactionOut(Schema):
    id              = Integer()
    descripotion    = String()
    amount          = Float()
    date            = Date()
    category        = String()
    type            = String()
    notes           = String()


class TransactionListOut(Schema):
    success      = Boolean()
    transactions = List(Nested(TransactionOut))
    total        = Integer()
