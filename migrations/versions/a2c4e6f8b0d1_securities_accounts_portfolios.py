"""securities accounts and portfolios (F42): each operation of a holding sits in a dossier and belongs to a portfolio

Revision ID: a2c4e6f8b0d1
Revises: f1b3d5a7c9e2
Create Date: 2026-11-09

"""
import sqlalchemy as sa
from alembic import op

revision = 'a2c4e6f8b0d1'
down_revision = 'f1b3d5a7c9e2'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'securities_accounts',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('name', sa.Text(), nullable=False, unique=True),
        sa.Column('broker', sa.String(length=80)),
        sa.Column('settlement_account_id', sa.Integer(), sa.ForeignKey('accounts.id', ondelete='SET NULL')),
        sa.Column('owner', sa.String(length=80)),
        sa.Column('tax_regime', sa.String(length=20), nullable=False, server_default='amministrato'),
        sa.Column('abroad', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('cost_method', sa.String(length=20), nullable=False, server_default='average'),
        sa.Column('fee_fixed', sa.Numeric(38, 2)),
        sa.Column('fee_percent', sa.Numeric(9, 4)),
        sa.Column('fee_min', sa.Numeric(38, 2)),
        sa.Column('fee_max', sa.Numeric(38, 2)),
        sa.Column('notes', sa.Text()),
        sa.Column('active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('created_at', sa.DateTime()),
    )
    op.create_index('ix_securities_accounts_settlement_account_id', 'securities_accounts', ['settlement_account_id'])
    op.create_table(
        'portfolios',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('name', sa.Text(), nullable=False, unique=True),
        sa.Column('description', sa.Text()),
        sa.Column('is_default', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('position', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('created_at', sa.DateTime()),
    )
    op.add_column('transactions', sa.Column('securities_account_id', sa.Integer(),
                                            sa.ForeignKey('securities_accounts.id', ondelete='SET NULL')))
    op.add_column('transactions', sa.Column('portfolio_id', sa.Integer(),
                                            sa.ForeignKey('portfolios.id', ondelete='SET NULL')))
    op.create_index('ix_transactions_securities_account_id', 'transactions', ['securities_account_id'])
    op.create_index('ix_transactions_portfolio_id', 'transactions', ['portfolio_id'])
    op.add_column('holdings', sa.Column('opening_account_id', sa.Integer(),
                                        sa.ForeignKey('securities_accounts.id', ondelete='SET NULL')))
    op.add_column('holdings', sa.Column('opening_portfolio_id', sa.Integer(),
                                        sa.ForeignKey('portfolios.id', ondelete='SET NULL')))

    # What the archive had before: one portfolio, «Portafoglio principale», and one securities account for each
    # account the operations of the holdings moved money on («Titoli Directa»), with its commissions and regime.
    op.execute("""
        INSERT INTO portfolios (name, is_default, position, active, created_at)
        SELECT 'Portafoglio principale', true, 0, true, now()
        WHERE EXISTS (SELECT 1 FROM transactions WHERE holding_id IS NOT NULL)
           OR EXISTS (SELECT 1 FROM holdings WHERE opening_quantity > 0)
    """)
    op.execute("""
        INSERT INTO securities_accounts (name, broker, settlement_account_id, owner, tax_regime, abroad,
                                         fee_fixed, fee_percent, fee_min, fee_max, active, created_at)
        SELECT 'Titoli ' || a.name, COALESCE(a.bank, a.name), a.id, a.owner, a.tax_regime, a.abroad,
               a.fee_fixed, a.fee_percent, a.fee_min, a.fee_max, true, now()
        FROM accounts a
        WHERE a.id IN (SELECT COALESCE(t.account_id, t.counter_account_id) FROM transactions t
                       WHERE t.holding_id IS NOT NULL)
    """)
    op.execute("""
        UPDATE transactions t SET
            portfolio_id = (SELECT id FROM portfolios WHERE is_default LIMIT 1),
            securities_account_id = (SELECT s.id FROM securities_accounts s
                                     WHERE s.settlement_account_id = COALESCE(t.account_id, t.counter_account_id))
        WHERE t.holding_id IS NOT NULL
    """)
    # a commission belongs where its trade is
    op.execute("""
        UPDATE transactions f SET portfolio_id = t.portfolio_id, securities_account_id = t.securities_account_id
        FROM transactions t WHERE f.fee_for_id = t.id
    """)
    op.execute("""
        UPDATE holdings h SET
            opening_portfolio_id = (SELECT id FROM portfolios WHERE is_default LIMIT 1),
            opening_account_id = (SELECT t.securities_account_id FROM transactions t
                                  WHERE t.holding_id = h.id AND t.securities_account_id IS NOT NULL
                                  ORDER BY t.date, t.id LIMIT 1)
        WHERE h.opening_quantity > 0
    """)


def downgrade():
    op.drop_column('holdings', 'opening_portfolio_id')
    op.drop_column('holdings', 'opening_account_id')
    op.drop_index('ix_transactions_portfolio_id', table_name='transactions')
    op.drop_index('ix_transactions_securities_account_id', table_name='transactions')
    op.drop_column('transactions', 'portfolio_id')
    op.drop_column('transactions', 'securities_account_id')
    op.drop_table('portfolios')
    op.drop_index('ix_securities_accounts_settlement_account_id', table_name='securities_accounts')
    op.drop_table('securities_accounts')
