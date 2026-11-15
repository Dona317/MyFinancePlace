"""F96: the securities account is the one place of the commission rule and the regime of the capital gains

The account form now writes them on the securities account linked to the account (its liquidity). A securities
account that has no rule of its own takes the one entered before on its settlement account; one still on the default
regime takes the settlement account's, when that one says «dichiarativo». The account's columns stay, read only as a
fallback for the data from before.

Revision ID: f4a6c8e0b2d5
Revises: e3c5a7b9d1f4
Create Date: 2026-11-15 12:00:00.000000

"""
from alembic import op

# revision identifiers, used by Alembic.
revision = 'f4a6c8e0b2d5'
down_revision = 'e3c5a7b9d1f4'
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        UPDATE securities_accounts AS s
           SET fee_fixed = a.fee_fixed, fee_percent = a.fee_percent, fee_min = a.fee_min, fee_max = a.fee_max
          FROM accounts AS a
         WHERE s.settlement_account_id = a.id
           AND s.fee_fixed IS NULL AND s.fee_percent IS NULL AND s.fee_min IS NULL AND s.fee_max IS NULL
           AND (a.fee_fixed IS NOT NULL OR a.fee_percent IS NOT NULL OR a.fee_min IS NOT NULL OR a.fee_max IS NOT NULL)
    """)
    op.execute("""
        UPDATE securities_accounts AS s
           SET tax_regime = a.tax_regime
          FROM accounts AS a
         WHERE s.settlement_account_id = a.id
           AND s.tax_regime = 'amministrato' AND a.tax_regime = 'dichiarativo'
    """)


def downgrade():
    # the values copied stay where they are: they were the same on both sides
    pass
