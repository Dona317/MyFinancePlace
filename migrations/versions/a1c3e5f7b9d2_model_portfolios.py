"""model portfolios: templates, their slots and the holdings placed in them (F19d)

Revision ID: a1c3e5f7b9d2
Revises: f8b0d2e4a6c7
Create Date: 2026-10-12

"""
import sqlalchemy as sa
from alembic import op

revision = 'a1c3e5f7b9d2'
down_revision = 'f8b0d2e4a6c7'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'portfolio_templates',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.Text(), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('band', sa.Numeric(precision=5, scale=2), server_default='5', nullable=False),
        sa.Column('active', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_table(
        'template_slots',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('template_id', sa.Integer(), nullable=False),
        sa.Column('position', sa.Integer(), nullable=False),
        sa.Column('label', sa.Text(), nullable=False),
        sa.Column('target', sa.Numeric(precision=6, scale=2), nullable=False),
        sa.Column('asset_class', sa.Text(), nullable=True),
        sa.Column('isin', sa.String(length=12), nullable=True),
        sa.Column('ticker', sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(['template_id'], ['portfolio_templates.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_template_slots_template_id'), 'template_slots', ['template_id'], unique=False)
    op.create_table(
        'slot_holdings',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('slot_id', sa.Integer(), nullable=False),
        sa.Column('holding_id', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['holding_id'], ['holdings.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['slot_id'], ['template_slots.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('slot_id', 'holding_id'),
    )
    op.create_index(op.f('ix_slot_holdings_holding_id'), 'slot_holdings', ['holding_id'], unique=False)
    op.create_index(op.f('ix_slot_holdings_slot_id'), 'slot_holdings', ['slot_id'], unique=False)


def downgrade():
    op.drop_table('slot_holdings')
    op.drop_table('template_slots')
    op.drop_table('portfolio_templates')
