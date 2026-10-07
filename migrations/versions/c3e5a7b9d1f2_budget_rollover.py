"""budget rollover: what is left (or overspent) moves to the next month

Revision ID: c3e5a7b9d1f2
Revises: b2d4f6a8c0e1
Create Date: 2026-10-07

"""
from alembic import op
import sqlalchemy as sa


revision = 'c3e5a7b9d1f2'
down_revision = 'b2d4f6a8c0e1'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('budgets', sa.Column('rollover_since', sa.Date(), nullable=True))


def downgrade():
    op.drop_column('budgets', 'rollover_since')
