from apiflask import Schema
from apiflask.fields import Boolean, String, Integer


class SuccessOut(Schema):
    success = Boolean(metadata={"example": True})
    message = String(metadata={"example": "Operation completed"})


class DeleteOut(Schema):
    success = Boolean(metadata={"example": True})
    deleted_id = Integer(metadata={"example": 1})
