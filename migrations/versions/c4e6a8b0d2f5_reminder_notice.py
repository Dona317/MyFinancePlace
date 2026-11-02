"""reminder notice: how many days before its date a reminder is announced (F33)

Revision ID: c4e6a8b0d2f5
Revises: a3c5e7f9b1d4
Create Date: 2026-11-02 15:00:00.000000

"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = 'c4e6a8b0d2f5'
down_revision = 'a3c5e7f9b1d4'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('reminders', schema=None) as batch_op:
        batch_op.add_column(sa.Column('notice_days', sa.Integer(), nullable=False, server_default='7'))


def downgrade():
    with op.batch_alter_table('reminders', schema=None) as batch_op:
        batch_op.drop_column('notice_days')
