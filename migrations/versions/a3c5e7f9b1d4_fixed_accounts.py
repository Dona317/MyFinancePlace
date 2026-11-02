"""fixed accounts: Contanti (in several currencies) and Debiti are always there (F30)

`fixed` marks the two accounts every archive has («cash», «debt»): their name and kind do not change and they are
not deleted. `opening_foreign` keeps the opening amounts of the cash in other currencies ({"CHF": 50}).

Revision ID: a3c5e7f9b1d4
Revises: e7a9c1b3d5f8
Create Date: 2026-11-02 12:00:00.000000

"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = 'a3c5e7f9b1d4'
down_revision = 'e7a9c1b3d5f8'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('accounts', schema=None) as batch_op:
        batch_op.add_column(sa.Column('fixed', sa.String(length=10), nullable=True))
        batch_op.add_column(sa.Column('opening_foreign', sa.JSON(), nullable=True))
        batch_op.create_index('ix_accounts_fixed', ['fixed'], unique=True)


def downgrade():
    with op.batch_alter_table('accounts', schema=None) as batch_op:
        batch_op.drop_index('ix_accounts_fixed')
        batch_op.drop_column('opening_foreign')
        batch_op.drop_column('fixed')
