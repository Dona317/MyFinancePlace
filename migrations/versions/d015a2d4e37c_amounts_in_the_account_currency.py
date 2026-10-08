"""amounts in the account currency

What the bank charged in the account's currency when a transaction is in another one (a USD payment with a
EUR card), on the leaving account and on the arriving account of a transfer. Empty = the exchange rate is used.

Revision ID: d015a2d4e37c
Revises: 944f14aecfd9
Create Date: 2026-09-30 19:47:53.735869

"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = 'd015a2d4e37c'
down_revision = '944f14aecfd9'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('transactions', schema=None) as batch_op:
        batch_op.add_column(sa.Column('account_amount', sa.Numeric(precision=38, scale=2), nullable=True))
        batch_op.add_column(sa.Column('counter_amount', sa.Numeric(precision=38, scale=2), nullable=True))



def downgrade():
    with op.batch_alter_table('transactions', schema=None) as batch_op:
        batch_op.drop_column('counter_amount')
        batch_op.drop_column('account_amount')

