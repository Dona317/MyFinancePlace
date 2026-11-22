"""transactions.reversal_id: an expense and an income that cancel each other (storno, F108)

Revision ID: e2a4c6e8f0b1
Revises: d8e0f2a4b6c9
Create Date: 2026-11-22 18:00:00.000000

"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = 'e2a4c6e8f0b1'
down_revision = 'd8e0f2a4b6c9'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('transactions', schema=None) as batch_op:
        batch_op.add_column(sa.Column('reversal_id', sa.Integer(), nullable=True))
        batch_op.create_index(batch_op.f('ix_transactions_reversal_id'), ['reversal_id'], unique=True)
        batch_op.create_foreign_key('fk_transactions_reversal_id', 'transactions', ['reversal_id'], ['id'],
                                    ondelete='SET NULL')


def downgrade():
    with op.batch_alter_table('transactions', schema=None) as batch_op:
        batch_op.drop_constraint('fk_transactions_reversal_id', type_='foreignkey')
        batch_op.drop_index(batch_op.f('ix_transactions_reversal_id'))
        batch_op.drop_column('reversal_id')
