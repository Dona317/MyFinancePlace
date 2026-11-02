"""debts: the asset they financed (mortgage → house), for its equity (F20)

Revision ID: d7f9b1c3e5a8
Revises: c5e7a9b1d3f6
Create Date: 2026-10-13

"""
import sqlalchemy as sa
from alembic import op

revision = 'd7f9b1c3e5a8'
down_revision = 'c5e7a9b1d3f6'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('debts', sa.Column('holding_id', sa.Integer(), nullable=True))
    op.create_index(op.f('ix_debts_holding_id'), 'debts', ['holding_id'], unique=False)
    op.create_foreign_key('debts_holding_id_fkey', 'debts', 'holdings', ['holding_id'], ['id'], ondelete='SET NULL')


def downgrade():
    op.drop_constraint('debts_holding_id_fkey', 'debts', type_='foreignkey')
    op.drop_index(op.f('ix_debts_holding_id'), table_name='debts')
    op.drop_column('debts', 'holding_id')
