"""accounts, holdings and debts: whose they are in the family (F20)

Revision ID: e9b1d3f5a7c0
Revises: d7f9b1c3e5a8
Create Date: 2026-10-13

"""
import sqlalchemy as sa
from alembic import op

revision = 'e9b1d3f5a7c0'
down_revision = 'd7f9b1c3e5a8'
branch_labels = None
depends_on = None

TABLES = ('accounts', 'holdings', 'debts')


def upgrade():
    for table in TABLES:
        op.add_column(table, sa.Column('owner', sa.String(length=80), nullable=True))


def downgrade():
    for table in TABLES:
        op.drop_column(table, 'owner')
