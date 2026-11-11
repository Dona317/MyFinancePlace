"""planned_orders: the theoretical orders of a rebalancing or a PAC instalment, until they are executed

Revision ID: e5a7b9c1d3f8
Revises: d4f6a8c0e2b7
Create Date: 2026-11-11

"""
import sqlalchemy as sa
from alembic import op

revision = 'e5a7b9c1d3f8'
down_revision = 'd4f6a8c0e2b7'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'planned_orders',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('batch', sa.String(length=32), nullable=False),
        sa.Column('source', sa.String(length=20), nullable=False),
        sa.Column('label', sa.Text(), nullable=True),
        sa.Column('holding_id', sa.Integer(), nullable=False),
        sa.Column('side', sa.String(length=4), nullable=False),
        sa.Column('units', sa.Numeric(38, 8), nullable=False),
        sa.Column('price', sa.Numeric(38, 6), nullable=False),
        sa.Column('account_id', sa.Integer(), nullable=True),
        sa.Column('securities_account_id', sa.Integer(), nullable=True),
        sa.Column('portfolio_id', sa.Integer(), nullable=True),
        sa.Column('plan_id', sa.Integer(), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['holding_id'], ['holdings.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['account_id'], ['accounts.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['securities_account_id'], ['securities_accounts.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['portfolio_id'], ['portfolios.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['plan_id'], ['investment_plans.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_planned_orders_batch', 'planned_orders', ['batch'])
    op.create_index('ix_planned_orders_holding_id', 'planned_orders', ['holding_id'])


def downgrade():
    op.drop_index('ix_planned_orders_holding_id', table_name='planned_orders')
    op.drop_index('ix_planned_orders_batch', table_name='planned_orders')
    op.drop_table('planned_orders')
