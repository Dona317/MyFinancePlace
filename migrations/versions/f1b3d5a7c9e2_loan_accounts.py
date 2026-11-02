"""loan accounts: a loan received has a debt account of its own (F34)

The money received is a giroconto from that account to the bank; the installments paid back reduce it.

Revision ID: f1b3d5a7c9e2
Revises: e8a0c2d4f6b9
Create Date: 2026-11-02 21:00:00.000000

"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = 'f1b3d5a7c9e2'
down_revision = 'e8a0c2d4f6b9'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('debts', schema=None) as batch_op:
        batch_op.add_column(sa.Column('account_id', sa.Integer(), nullable=True))
        batch_op.create_index('ix_debts_account_id', ['account_id'], unique=False)
        batch_op.create_foreign_key('fk_debts_account_id', 'accounts', ['account_id'], ['id'], ondelete='SET NULL')


def downgrade():
    with op.batch_alter_table('debts', schema=None) as batch_op:
        batch_op.drop_constraint('fk_debts_account_id', type_='foreignkey')
        batch_op.drop_index('ix_debts_account_id')
        batch_op.drop_column('account_id')
