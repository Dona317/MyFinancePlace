"""goals: linked account, monthly saving and expected return, for the projection (F20)

Revision ID: f1c3e5a7b9d2
Revises: e9b1d3f5a7c0
Create Date: 2026-10-13

"""
import sqlalchemy as sa
from alembic import op

revision = 'f1c3e5a7b9d2'
down_revision = 'e9b1d3f5a7c0'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('goals', sa.Column('account_id', sa.Integer(), nullable=True))
    op.add_column('goals', sa.Column('monthly_contribution', sa.Numeric(precision=38, scale=2), nullable=True))
    op.add_column('goals', sa.Column('expected_return', sa.Numeric(precision=6, scale=2), nullable=True))
    op.create_foreign_key('goals_account_id_fkey', 'goals', 'accounts', ['account_id'], ['id'], ondelete='SET NULL')


def downgrade():
    op.drop_constraint('goals_account_id_fkey', 'goals', type_='foreignkey')
    for name in ('expected_return', 'monthly_contribution', 'account_id'):
        op.drop_column('goals', name)
