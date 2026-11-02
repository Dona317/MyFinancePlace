"""split transactions: transaction_splits (category + amount per part)

Revision ID: a1c2e3f4b5d6
Revises: 270b797b5daf
Create Date: 2026-10-07

"""
import sqlalchemy as sa
from alembic import op

revision = 'a1c2e3f4b5d6'
down_revision = '270b797b5daf'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'transaction_splits',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('transaction_id', sa.Integer(), nullable=False),
        sa.Column('category', sa.Text(), nullable=True),
        sa.Column('amount', sa.Numeric(precision=38, scale=2), nullable=False),
        sa.ForeignKeyConstraint(['transaction_id'], ['transactions.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_transaction_splits_transaction_id'), 'transaction_splits', ['transaction_id'], unique=False)


def downgrade():
    op.drop_index(op.f('ix_transaction_splits_transaction_id'), table_name='transaction_splits')
    op.drop_table('transaction_splits')
