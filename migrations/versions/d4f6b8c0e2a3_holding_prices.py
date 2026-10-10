"""holding prices: the price history of each holding

Revision ID: d4f6b8c0e2a3
Revises: c3e5a7b9d1f2
Create Date: 2026-10-08

"""
import sqlalchemy as sa
from alembic import op

revision = 'd4f6b8c0e2a3'
down_revision = 'c3e5a7b9d1f2'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'holding_prices',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('holding_id', sa.Integer(), nullable=False),
        sa.Column('on', sa.Date(), nullable=False),
        sa.Column('price', sa.Numeric(precision=38, scale=6), nullable=False),
        sa.ForeignKeyConstraint(['holding_id'], ['holdings.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('holding_id', 'on'),
    )
    op.create_index(op.f('ix_holding_prices_holding_id'), 'holding_prices', ['holding_id'], unique=False)
    # the price each holding has today becomes the first point of its history
    op.execute("""
        INSERT INTO holding_prices (holding_id, "on", price)
        SELECT id, price_date, current_price FROM holdings
        WHERE current_price IS NOT NULL AND price_date IS NOT NULL
    """)


def downgrade():
    op.drop_index(op.f('ix_holding_prices_holding_id'), table_name='holding_prices')
    op.drop_table('holding_prices')
