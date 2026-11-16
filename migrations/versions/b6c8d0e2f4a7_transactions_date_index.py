"""transactions.date indexed: nearly every list, total and report filters or orders the transactions by date

Revision ID: b6c8d0e2f4a7
Revises: a5b7c9d1e3f6
Create Date: 2026-11-15 18:00:00.000000

"""
from alembic import op

# revision identifiers, used by Alembic.
revision = 'b6c8d0e2f4a7'
down_revision = 'a5b7c9d1e3f6'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('transactions', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_transactions_date'), ['date'], unique=False)


def downgrade():
    with op.batch_alter_table('transactions', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_transactions_date'))
