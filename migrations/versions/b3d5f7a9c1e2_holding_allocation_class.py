"""holdings: the asset class (azionario, obbligazionario, oro…) apart from the instrument (F70)

Revision ID: b3d5f7a9c1e2
Revises: a2c4e6f8b0d1
Create Date: 2026-11-09

"""
import sqlalchemy as sa
from alembic import op

revision = 'b3d5f7a9c1e2'
down_revision = 'a2c4e6f8b0d1'
branch_labels = None
depends_on = None


def upgrade():
    # empty for every holding: the class is estimated from the instrument and the name until the user sets it
    op.add_column('holdings', sa.Column('allocation_class', sa.String(length=40), nullable=True))


def downgrade():
    op.drop_column('holdings', 'allocation_class')
