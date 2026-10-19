"""contribution limits: pension fund, PIR and the user's own (F22)

Revision ID: c7e9a1b3d5f8
Revises: b5d7f9a1c3e6
Create Date: 2026-10-13

"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = 'c7e9a1b3d5f8'
down_revision = 'b5d7f9a1c3e6'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'contribution_limits',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.Text(), nullable=False),
        sa.Column('kind', sa.String(length=20), nullable=False),
        sa.Column('yearly', sa.Numeric(precision=38, scale=2), nullable=False),
        sa.Column('total', sa.Numeric(precision=38, scale=2), nullable=True),
        sa.Column('since_year', sa.Integer(), nullable=True),
        sa.Column('account_ids', postgresql.ARRAY(sa.Integer()), server_default='{}', nullable=False),
        sa.Column('holding_ids', postgresql.ARRAY(sa.Integer()), server_default='{}', nullable=False),
        sa.Column('category', sa.Text(), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )


def downgrade():
    op.drop_table('contribution_limits')
