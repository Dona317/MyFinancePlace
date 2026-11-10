"""holdings: the fund's characteristics — issuer, domicile, TER, distribution, replication, index, launch date,
currency hedging — all editable

Revision ID: e6a8c0d2f4b5
Revises: d5f7b9c1e3a4
Create Date: 2026-11-10

"""
import sqlalchemy as sa
from alembic import op

revision = 'e6a8c0d2f4b5'
down_revision = 'd5f7b9c1e3a4'
branch_labels = None
depends_on = None

COLUMNS = [
    sa.Column('issuer', sa.String(length=80)),
    sa.Column('domicile', sa.String(length=2)),
    sa.Column('ter', sa.Numeric(6, 3)),
    sa.Column('distribution', sa.String(length=12)),
    sa.Column('replication', sa.String(length=12)),
    sa.Column('index_name', sa.Text()),
    sa.Column('launch_date', sa.Date()),
    sa.Column('currency_hedged', sa.Boolean(), nullable=False, server_default='false'),
]


def upgrade():
    for column in COLUMNS:
        op.add_column('holdings', column)


def downgrade():
    for column in reversed(COLUMNS):
        op.drop_column('holdings', column.name)
