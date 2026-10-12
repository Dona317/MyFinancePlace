"""holdings: the instrument (ISIN, quote currency, exchange, multiplier, price source)

Revision ID: e7a9c1d3f5b8
Revises: d5f7b9c1e3a6
Create Date: 2026-10-12

"""
import sqlalchemy as sa
from alembic import op

revision = 'e7a9c1d3f5b8'
down_revision = 'd5f7b9c1e3a6'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('holdings', sa.Column('isin', sa.String(length=12), nullable=True))
    op.add_column('holdings', sa.Column('currency', sa.String(length=3), nullable=True))
    op.add_column('holdings', sa.Column('exchange', sa.Text(), nullable=True))
    op.add_column('holdings', sa.Column('multiplier', sa.Numeric(precision=18, scale=6), nullable=False,
                                        server_default='1'))
    op.add_column('holdings', sa.Column('price_source', sa.String(length=20), nullable=False, server_default='auto'))


def downgrade():
    for name in ('price_source', 'multiplier', 'exchange', 'currency', 'isin'):
        op.drop_column('holdings', name)
