"""holdings: yearly depreciation; prices: the valuation's note and the estimated points (F22)

Revision ID: e1d3f5b7c9a2
Revises: d9b1c3e5f7a0
Create Date: 2026-10-13

"""
import sqlalchemy as sa
from alembic import op

revision = 'e1d3f5b7c9a2'
down_revision = 'd9b1c3e5f7a0'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('holdings', sa.Column('depreciation_rate', sa.Numeric(precision=6, scale=2), nullable=True))
    op.add_column('holding_prices', sa.Column('note', sa.Text(), nullable=True))
    op.add_column('holding_prices', sa.Column('estimated', sa.Boolean(), server_default='false', nullable=False))


def downgrade():
    op.drop_column('holding_prices', 'estimated')
    op.drop_column('holding_prices', 'note')
    op.drop_column('holdings', 'depreciation_rate')
