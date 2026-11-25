"""holdings: an option's terms — call or put, strike, expiry, underlying, style, settlement (F120)

Revision ID: f3b5d7e9a1c2
Revises: e2a4c6e8f0b1
Create Date: 2026-11-25 10:00:00.000000

"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = 'f3b5d7e9a1c2'
down_revision = 'e2a4c6e8f0b1'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('holdings', schema=None) as batch_op:
        batch_op.add_column(sa.Column('option_kind', sa.String(length=4), nullable=True))
        batch_op.add_column(sa.Column('strike', sa.Numeric(precision=18, scale=6), nullable=True))
        batch_op.add_column(sa.Column('option_expiry', sa.Date(), nullable=True))
        batch_op.add_column(sa.Column('underlying', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('exercise_style', sa.String(length=10), nullable=True))
        batch_op.add_column(sa.Column('settlement', sa.String(length=10), nullable=True))


def downgrade():
    with op.batch_alter_table('holdings', schema=None) as batch_op:
        for column in ('settlement', 'exercise_style', 'underlying', 'option_expiry', 'strike', 'option_kind'):
            batch_op.drop_column(column)
