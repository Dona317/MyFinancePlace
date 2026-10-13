"""categories: left out of the analyses (F22)

Revision ID: d9b1c3e5f7a0
Revises: c7e9a1b3d5f8
Create Date: 2026-10-13

"""
import sqlalchemy as sa
from alembic import op

revision = 'd9b1c3e5f7a0'
down_revision = 'c7e9a1b3d5f8'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('categories', sa.Column('excluded', sa.Boolean(), server_default='false', nullable=False))


def downgrade():
    op.drop_column('categories', 'excluded')
