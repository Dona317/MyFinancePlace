"""cards: debit, credit and prepaid cards charged on an account (the full number only encrypted), and the card of a
movement (F41)

Revision ID: f6b8c0d2e4a9
Revises: e5a7b9c1d3f8
Create Date: 2026-11-12

"""
import sqlalchemy as sa
from alembic import op

revision = 'f6b8c0d2e4a9'
down_revision = 'e5a7b9c1d3f8'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'cards',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.Text(), nullable=False),
        sa.Column('kind', sa.String(length=10), nullable=False),
        sa.Column('network', sa.String(length=12), nullable=True),
        sa.Column('last4', sa.String(length=4), nullable=True),
        sa.Column('number_enc', sa.Text(), nullable=True),
        sa.Column('expiry_month', sa.SmallInteger(), nullable=True),
        sa.Column('expiry_year', sa.SmallInteger(), nullable=True),
        sa.Column('holder', sa.String(length=80), nullable=True),
        sa.Column('account_id', sa.Integer(), nullable=True),
        sa.Column('credit_limit', sa.Numeric(14, 2), nullable=True),
        sa.Column('statement_day', sa.SmallInteger(), nullable=True),
        sa.Column('contactless', sa.Boolean(), server_default='true', nullable=False),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('active', sa.Boolean(), server_default='true', nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['account_id'], ['accounts.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_cards_account_id', 'cards', ['account_id'])
    with op.batch_alter_table('transactions') as batch:
        batch.add_column(sa.Column('card_id', sa.Integer(), nullable=True))
        batch.create_foreign_key('fk_transactions_card', 'cards', ['card_id'], ['id'], ondelete='SET NULL')
        batch.create_index('ix_transactions_card_id', ['card_id'])


def downgrade():
    with op.batch_alter_table('transactions') as batch:
        batch.drop_index('ix_transactions_card_id')
        batch.drop_constraint('fk_transactions_card', type_='foreignkey')
        batch.drop_column('card_id')
    op.drop_index('ix_cards_account_id', table_name='cards')
    op.drop_table('cards')
