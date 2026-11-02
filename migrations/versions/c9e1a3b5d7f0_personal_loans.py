"""money lent to and borrowed from people (F22)

Revision ID: c9e1a3b5d7f0
Revises: b7d9f1a3c5e8
Create Date: 2026-10-13

"""
import sqlalchemy as sa
from alembic import op

revision = 'c9e1a3b5d7f0'
down_revision = 'b7d9f1a3c5e8'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'personal_loans',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('person', sa.Text(), nullable=False),
        sa.Column('date', sa.Date(), nullable=False),
        sa.Column('amount', sa.Numeric(precision=38, scale=2), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('due', sa.Date(), nullable=True),
        sa.Column('transaction_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['transaction_id'], ['transactions.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_personal_loans_person'), 'personal_loans', ['person'], unique=False)


def downgrade():
    op.drop_index(op.f('ix_personal_loans_person'), table_name='personal_loans')
    op.drop_table('personal_loans')
