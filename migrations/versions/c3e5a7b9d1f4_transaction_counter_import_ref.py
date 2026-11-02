"""transactions: the other statement's row of a transfer between own accounts

Revision ID: c3e5a7b9d1f4
Revises: b1d3f5a7c9e2
Create Date: 2026-10-10

"""
import sqlalchemy as sa
from alembic import op

revision = 'c3e5a7b9d1f4'
down_revision = 'b1d3f5a7c9e2'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('transactions', sa.Column('counter_import_ref', sa.String(length=64), nullable=True))
    op.create_index(op.f('ix_transactions_counter_import_ref'), 'transactions', ['counter_import_ref'], unique=True)


def downgrade():
    op.drop_index(op.f('ix_transactions_counter_import_ref'), table_name='transactions')
    op.drop_column('transactions', 'counter_import_ref')
