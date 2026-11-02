"""
Classifications of the user's own (F22): besides region and sector, any way of grouping the holdings — risk, theme,
ESG, whose PAC it is — with categories, and each holding in one category or split among several by percentage
(an ETF 60 % in one, 40 % in another).
"""
from app.extensions import db


class Taxonomy(db.Model):
    __tablename__ = "taxonomies"

    id       = db.Column(db.Integer, primary_key=True)
    name     = db.Column(db.Text, nullable=False, unique=True)
    multiple = db.Column(db.Boolean, nullable=False, default=False)  # a holding split among categories by %
    position = db.Column(db.Integer, nullable=False, default=0)
    categories = db.relationship("TaxonomyCategory", back_populates="taxonomy", cascade="all, delete-orphan",
                                 passive_deletes=True, order_by="TaxonomyCategory.position, TaxonomyCategory.id")


class TaxonomyCategory(db.Model):
    __tablename__ = "taxonomy_categories"
    __table_args__ = (db.UniqueConstraint("taxonomy_id", "name"),)

    id          = db.Column(db.Integer, primary_key=True)
    taxonomy_id = db.Column(db.Integer, db.ForeignKey("taxonomies.id", ondelete="CASCADE"), nullable=False, index=True)
    name        = db.Column(db.Text, nullable=False)
    position    = db.Column(db.Integer, nullable=False, default=0)
    taxonomy    = db.relationship("Taxonomy", back_populates="categories")


class HoldingCategory(db.Model):
    """A holding in a category, for this share of its value (100 for a single choice)."""
    __tablename__ = "holding_categories"

    holding_id  = db.Column(db.Integer, db.ForeignKey("holdings.id", ondelete="CASCADE"), primary_key=True)
    category_id = db.Column(db.Integer, db.ForeignKey("taxonomy_categories.id", ondelete="CASCADE"), primary_key=True)
    weight      = db.Column(db.Numeric(6, 2), nullable=False, default=100)
