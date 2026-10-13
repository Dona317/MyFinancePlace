from app.extensions import db


class DuplicateDismissal(db.Model):
    """A pair of transactions the user confirmed are NOT duplicates (hidden from the duplicate finder)."""
    __tablename__ = "duplicate_dismissals"
    __table_args__ = (
        db.UniqueConstraint("first_id", "second_id"),
        db.CheckConstraint("first_id < second_id", name="ck_duplicate_dismissals_ordered"),
    )

    id        = db.Column(db.Integer, primary_key=True)
    first_id  = db.Column(db.Integer, db.ForeignKey("transactions.id", ondelete="CASCADE"), nullable=False)
    second_id = db.Column(db.Integer, db.ForeignKey("transactions.id", ondelete="CASCADE"), nullable=False)
