"""studio: clients, each with a database of its own

Revision ID: f6b8d0e2a4c5
Revises: e5a7c9e1f3b4
Create Date: 2026-10-08

"""
import sqlalchemy as sa
from alembic import op

revision = 'f6b8d0e2a4c5'
down_revision = 'e5a7c9e1f3b4'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'clients',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=120), nullable=False),
        sa.Column('slug', sa.String(length=40), nullable=False),
        sa.Column('database', sa.String(length=63), nullable=True),
        sa.Column('color', sa.String(length=7), nullable=False),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('archived', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('slug'),
    )


def downgrade():
    op.drop_table('clients')
