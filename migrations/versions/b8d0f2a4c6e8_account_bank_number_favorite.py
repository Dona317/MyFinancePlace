"""accounts: bank, account number and the favourite one

The bank's name (several accounts of the same bank: «Fineco 1», «Fineco 2»), the account number kept whole, and
the favourite account, proposed when a statement is imported.

Revision ID: b8d0f2a4c6e8
Revises: a7c9e1b3d5f6
Create Date: 2026-10-31 18:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b8d0f2a4c6e8'
down_revision = 'a7c9e1b3d5f6'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('accounts', schema=None) as batch_op:
        batch_op.add_column(sa.Column('bank', sa.String(length=80), nullable=True))
        batch_op.add_column(sa.Column('account_number', sa.String(length=40), nullable=True))
        batch_op.add_column(sa.Column('favorite', sa.Boolean(), nullable=False, server_default='false'))


def downgrade():
    with op.batch_alter_table('accounts', schema=None) as batch_op:
        batch_op.drop_column('favorite')
        batch_op.drop_column('account_number')
        batch_op.drop_column('bank')
