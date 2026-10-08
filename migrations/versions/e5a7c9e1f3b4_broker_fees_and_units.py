"""broker fee rules on accounts; trades in units with their commission

Revision ID: e5a7c9e1f3b4
Revises: d4f6b8c0e2a3
Create Date: 2026-10-08

"""
from alembic import op
import sqlalchemy as sa


revision = 'e5a7c9e1f3b4'
down_revision = 'd4f6b8c0e2a3'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('accounts', sa.Column('fee_fixed', sa.Numeric(precision=38, scale=2), nullable=True))
    op.add_column('accounts', sa.Column('fee_percent', sa.Numeric(precision=9, scale=4), nullable=True))
    op.add_column('accounts', sa.Column('fee_min', sa.Numeric(precision=38, scale=2), nullable=True))
    op.add_column('accounts', sa.Column('fee_max', sa.Numeric(precision=38, scale=2), nullable=True))
    op.add_column('transactions', sa.Column('units', sa.Numeric(precision=38, scale=8), nullable=True))
    op.add_column('transactions', sa.Column('unit_price', sa.Numeric(precision=38, scale=6), nullable=True))
    op.add_column('transactions', sa.Column('fee_for_id', sa.Integer(), nullable=True))
    op.create_index(op.f('ix_transactions_fee_for_id'), 'transactions', ['fee_for_id'], unique=False)
    op.create_foreign_key('fk_transactions_fee_for_id', 'transactions', 'transactions', ['fee_for_id'], ['id'],
                          ondelete='CASCADE')


def downgrade():
    op.drop_constraint('fk_transactions_fee_for_id', 'transactions', type_='foreignkey')
    op.drop_index(op.f('ix_transactions_fee_for_id'), table_name='transactions')
    op.drop_column('transactions', 'fee_for_id')
    op.drop_column('transactions', 'unit_price')
    op.drop_column('transactions', 'units')
    op.drop_column('accounts', 'fee_max')
    op.drop_column('accounts', 'fee_min')
    op.drop_column('accounts', 'fee_percent')
    op.drop_column('accounts', 'fee_fixed')
