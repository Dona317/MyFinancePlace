"""utility bills and consumption (F23)

Revision ID: a7c9e1b3d5f6
Revises: f3b5d7a9c1e4
Create Date: 2026-10-19

"""
import sqlalchemy as sa
from alembic import op

revision = 'a7c9e1b3d5f6'
down_revision = 'f3b5d7a9c1e4'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'utility_readings',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('utility', sa.String(length=20), nullable=False),
        sa.Column('supplier', sa.Text(), nullable=True),
        sa.Column('period_start', sa.Date(), nullable=False),
        sa.Column('period_end', sa.Date(), nullable=False),
        sa.Column('consumption', sa.Numeric(precision=14, scale=3), nullable=True),
        sa.Column('amount', sa.Numeric(precision=38, scale=2), nullable=False),
        sa.Column('transaction_id', sa.Integer(), nullable=True),
        sa.Column('document_id', sa.Integer(), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['transaction_id'], ['transactions.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['document_id'], ['documents.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('utility_readings') as batch:
        batch.create_index(batch.f('ix_utility_readings_transaction_id'), ['transaction_id'], unique=False)


def downgrade():
    with op.batch_alter_table('utility_readings') as batch:
        batch.drop_index(batch.f('ix_utility_readings_transaction_id'))
    op.drop_table('utility_readings')
