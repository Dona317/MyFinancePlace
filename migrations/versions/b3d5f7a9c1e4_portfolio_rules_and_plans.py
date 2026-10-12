"""portfolio rules (alerts) and investment plans (PAC) (F19e)

Revision ID: b3d5f7a9c1e4
Revises: a1c3e5f7b9d2
Create Date: 2026-10-12

"""
import sqlalchemy as sa
from alembic import op

revision = 'b3d5f7a9c1e4'
down_revision = 'a1c3e5f7b9d2'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'portfolio_rules',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('kind', sa.String(length=20), nullable=False),
        sa.Column('holding_id', sa.Integer(), nullable=True),
        sa.Column('threshold', sa.Numeric(precision=18, scale=6), nullable=True),
        sa.Column('active', sa.Boolean(), server_default='true', nullable=False),
        sa.ForeignKeyConstraint(['holding_id'], ['holdings.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_portfolio_rules_holding_id'), 'portfolio_rules', ['holding_id'], unique=False)
    op.create_table(
        'investment_plans',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.Text(), nullable=False),
        sa.Column('amount', sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column('frequency', sa.String(length=10), nullable=False),
        sa.Column('day', sa.Integer(), nullable=False),
        sa.Column('account_id', sa.Integer(), nullable=True),
        sa.Column('template_id', sa.Integer(), nullable=True),
        sa.Column('fractional', sa.Boolean(), server_default='true', nullable=False),
        sa.Column('start', sa.Date(), nullable=False),
        sa.Column('end', sa.Date(), nullable=True),
        sa.Column('last_done', sa.String(length=7), nullable=True),
        sa.ForeignKeyConstraint(['account_id'], ['accounts.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['template_id'], ['portfolio_templates.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )


def downgrade():
    op.drop_table('investment_plans')
    op.drop_table('portfolio_rules')
