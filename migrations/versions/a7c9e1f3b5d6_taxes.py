"""taxes: capital gains regime and foreign flag on accounts; tax rate and foreign flag on holdings

Revision ID: a7c9e1f3b5d6
Revises: f6b8d0e2a4c5
Create Date: 2026-10-08

"""
from alembic import op
import sqlalchemy as sa


revision = 'a7c9e1f3b5d6'
down_revision = 'f6b8d0e2a4c5'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('accounts', sa.Column('tax_regime', sa.String(length=20), nullable=False, server_default='amministrato'))
    op.add_column('accounts', sa.Column('abroad', sa.Boolean(), nullable=False, server_default='false'))
    op.add_column('holdings', sa.Column('tax_rate', sa.Numeric(precision=5, scale=2), nullable=True))
    op.add_column('holdings', sa.Column('abroad', sa.Boolean(), nullable=False, server_default='false'))


def downgrade():
    op.drop_column('holdings', 'abroad')
    op.drop_column('holdings', 'tax_rate')
    op.drop_column('accounts', 'abroad')
    op.drop_column('accounts', 'tax_regime')
