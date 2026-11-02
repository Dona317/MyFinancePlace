from datetime import datetime

from app.extensions import db


class ClusterRule(db.Model):
    """
    "Transactions whose description or counterparty contains this word belong to this cluster" (the group
    above the category: Necessità, Scelte e svago, Risparmio). Learned when the user sets a cluster by hand.
    """
    __tablename__ = "cluster_rules"

    id         = db.Column(db.Integer, primary_key=True)
    keyword    = db.Column(db.Text, nullable=False, unique=True)   # normalized: lowercase words and numbers
    cluster    = db.Column(db.String(20), nullable=False)          # see services.clusters.CLUSTERS
    source     = db.Column(db.String(10), nullable=False, default="manual")  # "manual" | "learned"
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.now)
