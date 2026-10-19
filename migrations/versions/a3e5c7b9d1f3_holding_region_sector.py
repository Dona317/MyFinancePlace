"""holdings: region and sector, for the exposure of the portfolio (F20)

Revision ID: a3e5c7b9d1f3
Revises: f1c3e5a7b9d2
Create Date: 2026-10-13

"""
import sqlalchemy as sa
from alembic import op

revision = 'a3e5c7b9d1f3'
down_revision = 'f1c3e5a7b9d2'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('holdings', sa.Column('region', sa.Text(), nullable=True))
    op.add_column('holdings', sa.Column('sector', sa.Text(), nullable=True))


def downgrade():
    op.drop_column('holdings', 'sector')
    op.drop_column('holdings', 'region')
