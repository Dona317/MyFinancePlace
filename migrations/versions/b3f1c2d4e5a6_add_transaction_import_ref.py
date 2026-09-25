"""add transaction import_ref

Revision ID: b3f1c2d4e5a6
Revises: 86c8730102a7
Create Date: 2026-09-25 09:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b3f1c2d4e5a6'
down_revision = '86c8730102a7'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('transactions', schema=None) as batch_op:
        batch_op.add_column(sa.Column('import_ref', sa.String(length=64), nullable=True))
        batch_op.create_index(batch_op.f('ix_transactions_import_ref'), ['import_ref'], unique=True)


def downgrade():
    with op.batch_alter_table('transactions', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_transactions_import_ref'))
        batch_op.drop_column('import_ref')
