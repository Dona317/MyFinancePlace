"""add transaction bank_description (the bank's original causale)

Revision ID: d4e8a1b2c3f5
Revises: c7d2e9f1a3b4
Create Date: 2026-09-25 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'd4e8a1b2c3f5'
down_revision = 'c7d2e9f1a3b4'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('transactions', schema=None) as batch_op:
        batch_op.add_column(sa.Column('bank_description', sa.Text(), nullable=True))
    # Transactions imported before this column existed: their description is still the bank's text
    op.execute("UPDATE transactions SET bank_description = description WHERE 'importato' = ANY(tags)")


def downgrade():
    with op.batch_alter_table('transactions', schema=None) as batch_op:
        batch_op.drop_column('bank_description')
