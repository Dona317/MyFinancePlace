"""odd jobs and occasional work (F22)

Revision ID: b7d9f1a3c5e8
Revises: a5c7e9b1d3f6
Create Date: 2026-10-13

"""
import sqlalchemy as sa
from alembic import op

revision = 'b7d9f1a3c5e8'
down_revision = 'a5c7e9b1d3f6'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'gigs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('client', sa.Text(), nullable=False),
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column('owner', sa.String(length=80), nullable=True),
        sa.Column('date', sa.Date(), nullable=False),
        sa.Column('hours', sa.Numeric(precision=9, scale=2), nullable=True),
        sa.Column('gross', sa.Numeric(precision=38, scale=2), nullable=False),
        sa.Column('withholding_rate', sa.Numeric(precision=5, scale=2), nullable=False),
        sa.Column('expenses', sa.Numeric(precision=38, scale=2), nullable=False),
        sa.Column('method', sa.String(length=20), nullable=False),
        sa.Column('paid_on', sa.Date(), nullable=True),
        sa.Column('transaction_id', sa.Integer(), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['transaction_id'], ['transactions.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )


def downgrade():
    op.drop_table('gigs')
