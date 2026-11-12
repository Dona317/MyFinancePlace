"""holding_prices.price_ccy, currency, fx_rate: the price as quoted in its own currency and the rate used (F43)

Revision ID: a7c9e1f3b5d8
Revises: f6b8c0d2e4a9
Create Date: 2026-11-12

"""
import sqlalchemy as sa
from alembic import op

revision = 'a7c9e1f3b5d8'
down_revision = 'f6b8c0d2e4a9'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('holding_prices') as batch:
        batch.add_column(sa.Column('price_ccy', sa.Numeric(38, 6), nullable=True))
        batch.add_column(sa.Column('currency', sa.String(length=3), nullable=True))
        batch.add_column(sa.Column('fx_rate', sa.Numeric(18, 8), nullable=True))


def downgrade():
    with op.batch_alter_table('holding_prices') as batch:
        batch.drop_column('fx_rate')
        batch.drop_column('currency')
        batch.drop_column('price_ccy')
