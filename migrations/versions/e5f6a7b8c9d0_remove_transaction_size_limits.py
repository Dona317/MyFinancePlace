"""remove size limits on transaction text and amount columns

description/category/counterparty: VARCHAR(255/100/255) -> TEXT (no length limit)
amount: NUMERIC(12, 2) (max 9,999,999,999.99) -> NUMERIC(38, 2)
Also clears the frequency wrongly stored on non-recurring transactions.

Revision ID: e5f6a7b8c9d0
Revises: d4e8a1b2c3f5
Create Date: 2026-09-25 14:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'e5f6a7b8c9d0'
down_revision = 'd4e8a1b2c3f5'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('transactions', schema=None) as batch_op:
        batch_op.alter_column('description', existing_type=sa.String(length=255), type_=sa.Text(), existing_nullable=False)
        batch_op.alter_column('category', existing_type=sa.String(length=100), type_=sa.Text(), existing_nullable=True)
        batch_op.alter_column('counterparty', existing_type=sa.String(length=255), type_=sa.Text(), existing_nullable=True)
        batch_op.alter_column('amount', existing_type=sa.Numeric(12, 2), type_=sa.Numeric(38, 2), existing_nullable=False)
    # Data fix: the transaction form used to store "monthly" on non-recurring transactions too
    op.execute("UPDATE transactions SET recurrence = NULL, recurrence_end = NULL WHERE NOT COALESCE(is_recurring, FALSE)")


def downgrade():
    # Values longer/larger than the old limits would not fit: truncate text, refuse oversized amounts
    op.execute("UPDATE transactions SET description = LEFT(description, 255), category = LEFT(category, 100), "
               "counterparty = LEFT(counterparty, 255)")
    with op.batch_alter_table('transactions', schema=None) as batch_op:
        batch_op.alter_column('amount', existing_type=sa.Numeric(38, 2), type_=sa.Numeric(12, 2), existing_nullable=False)
        batch_op.alter_column('counterparty', existing_type=sa.Text(), type_=sa.String(length=255), existing_nullable=True)
        batch_op.alter_column('category', existing_type=sa.Text(), type_=sa.String(length=100), existing_nullable=True)
        batch_op.alter_column('description', existing_type=sa.Text(), type_=sa.String(length=255), existing_nullable=False)
