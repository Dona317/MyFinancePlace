"""holdings: a bond's terms — type, coupon rate and frequency, maturity, redemption, first coupon date, issue
price — all editable (services.bonds)

Revision ID: f7b9d1e3a5c6
Revises: e6a8c0d2f4b5
Create Date: 2026-11-10

"""
import sqlalchemy as sa
from alembic import op

revision = 'f7b9d1e3a5c6'
down_revision = 'e6a8c0d2f4b5'
branch_labels = None
depends_on = None

COLUMNS = [
    sa.Column('bond_type', sa.String(length=20)),
    sa.Column('coupon_rate', sa.Numeric(7, 4)),
    sa.Column('coupon_frequency', sa.SmallInteger()),
    sa.Column('maturity_date', sa.Date()),
    sa.Column('redemption', sa.Numeric(7, 3)),
    sa.Column('first_coupon_date', sa.Date()),
    sa.Column('issue_price', sa.Numeric(9, 4)),
]


def upgrade():
    for column in COLUMNS:
        op.add_column('holdings', column)


def downgrade():
    for column in reversed(COLUMNS):
        op.drop_column('holdings', column.name)
