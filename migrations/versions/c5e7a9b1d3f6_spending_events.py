"""spending events: trips, weddings, renovations gathering movements of any category (F20)

Revision ID: c5e7a9b1d3f6
Revises: b3d5f7a9c1e4
Create Date: 2026-10-13

"""
import sqlalchemy as sa
from alembic import op

revision = 'c5e7a9b1d3f6'
down_revision = 'b3d5f7a9c1e4'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'spending_events',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.Text(), nullable=False),
        sa.Column('start', sa.Date(), nullable=False),
        sa.Column('end', sa.Date(), nullable=True),
        sa.Column('budget', sa.Numeric(precision=38, scale=2), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.add_column('transactions', sa.Column('event_id', sa.Integer(), nullable=True))
    op.create_index(op.f('ix_transactions_event_id'), 'transactions', ['event_id'], unique=False)
    op.create_foreign_key('transactions_event_id_fkey', 'transactions', 'spending_events', ['event_id'], ['id'],
                          ondelete='SET NULL')


def downgrade():
    op.drop_constraint('transactions_event_id_fkey', 'transactions', type_='foreignkey')
    op.drop_index(op.f('ix_transactions_event_id'), table_name='transactions')
    op.drop_column('transactions', 'event_id')
    op.drop_table('spending_events')
