"""cards: the debit, credit and prepaid cards of an account (F41)

Revision ID: a9c1e3b5d7f0
Revises: f1b3d5a7c9e2
Create Date: 2026-11-02 22:00:00.000000

"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = 'a9c1e3b5d7f0'
down_revision = 'f1b3d5a7c9e2'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'cards',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('account_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.Text(), nullable=False),
        sa.Column('kind', sa.String(length=10), nullable=False),
        sa.Column('last4', sa.String(length=4), nullable=True),
        sa.Column('position', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['account_id'], ['accounts.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('cards', schema=None) as batch_op:
        batch_op.create_index('ix_cards_account_id', ['account_id'], unique=False)


def downgrade():
    with op.batch_alter_table('cards', schema=None) as batch_op:
        batch_op.drop_index('ix_cards_account_id')
    op.drop_table('cards')
