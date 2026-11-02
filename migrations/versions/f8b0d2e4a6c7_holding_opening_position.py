"""holdings: the opening position (what was held before the operations recorded)

Revision ID: f8b0d2e4a6c7
Revises: e7a9c1d3f5b8
Create Date: 2026-10-12

"""
import sqlalchemy as sa
from alembic import op

revision = 'f8b0d2e4a6c7'
down_revision = 'e7a9c1d3f5b8'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('holdings', sa.Column('opening_quantity', sa.Numeric(precision=38, scale=8), nullable=True))
    op.add_column('holdings', sa.Column('opening_price', sa.Numeric(precision=38, scale=6), nullable=True))
    op.add_column('holdings', sa.Column('opening_date', sa.Date(), nullable=True))
    # what each holding held before its recorded trades, at its average price (as the capital gains always assumed)
    op.execute("""
        UPDATE holdings h SET
            opening_quantity = GREATEST(h.quantity - COALESCE((
                SELECT SUM(t.units) FROM transactions t
                WHERE t.holding_id = h.id AND t.units IS NOT NULL AND t.unit_price IS NOT NULL), 0), 0),
            opening_price = h.avg_price,
            opening_date = h.purchase_date
    """)


def downgrade():
    for name in ('opening_date', 'opening_price', 'opening_quantity'):
        op.drop_column('holdings', name)
