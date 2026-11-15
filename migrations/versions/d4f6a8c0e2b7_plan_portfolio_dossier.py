"""investment_plans.portfolio_id and securities_account_id: a PAC that buys for one portfolio, in one securities
account (F52)

Revision ID: d4f6a8c0e2b7
Revises: a1c3e5b7d9f2
Create Date: 2026-11-11

"""
import sqlalchemy as sa
from alembic import op

revision = 'd4f6a8c0e2b7'
down_revision = 'a1c3e5b7d9f2'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('investment_plans') as batch:
        batch.add_column(sa.Column('portfolio_id', sa.Integer(), nullable=True))
        batch.add_column(sa.Column('securities_account_id', sa.Integer(), nullable=True))
        batch.create_foreign_key('fk_investment_plans_portfolio', 'portfolios', ['portfolio_id'], ['id'],
                                 ondelete='SET NULL')
        batch.create_foreign_key('fk_investment_plans_securities_account', 'securities_accounts',
                                 ['securities_account_id'], ['id'], ondelete='SET NULL')


def downgrade():
    with op.batch_alter_table('investment_plans') as batch:
        batch.drop_constraint('fk_investment_plans_securities_account', type_='foreignkey')
        batch.drop_constraint('fk_investment_plans_portfolio', type_='foreignkey')
        batch.drop_column('securities_account_id')
        batch.drop_column('portfolio_id')
