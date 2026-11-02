"""holdings: room for a price source of the user's own, «custom:<name>» (F22)

Revision ID: f3a5c7e9b1d4
Revises: e1d3f5b7c9a2
Create Date: 2026-10-13

"""
import sqlalchemy as sa
from alembic import op

revision = 'f3a5c7e9b1d4'
down_revision = 'e1d3f5b7c9a2'
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column('holdings', 'price_source', type_=sa.String(length=60), existing_type=sa.String(length=20),
                    existing_nullable=False, existing_server_default='auto')


def downgrade():
    op.alter_column('holdings', 'price_source', type_=sa.String(length=20), existing_type=sa.String(length=60),
                    existing_nullable=False, existing_server_default='auto')
