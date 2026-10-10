"""accounts: the full IBAN, to recognize bonifici between own accounts

Revision ID: d5f7b9c1e3a6
Revises: c3e5a7b9d1f4
Create Date: 2026-10-10

"""
import sqlalchemy as sa
from alembic import op

revision = 'd5f7b9c1e3a6'
down_revision = 'c3e5a7b9d1f4'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('accounts', sa.Column('iban', sa.String(length=34), nullable=True))


def downgrade():
    op.drop_column('accounts', 'iban')
