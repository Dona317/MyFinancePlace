"""deadlines written by hand (F23)

Revision ID: d1f3a5c7e9b2
Revises: c9e1a3b5d7f0
Create Date: 2026-10-19

"""
import sqlalchemy as sa
from alembic import op

revision = 'd1f3a5c7e9b2'
down_revision = 'c9e1a3b5d7f0'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'reminders',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('title', sa.Text(), nullable=False),
        sa.Column('due', sa.Date(), nullable=False),
        sa.Column('repeat', sa.String(length=10), nullable=False),
        sa.Column('amount', sa.Numeric(precision=38, scale=2), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('done', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )


def downgrade():
    op.drop_table('reminders')
