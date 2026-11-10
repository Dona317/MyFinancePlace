"""merge: the cards (F41) and the portfolio's securities accounts and exposures meet in one head

Revision ID: d2b4f6a8c0e3
Revises: a1c3e5b7d9f2, a9c1e3b5d7f0
Create Date: 2026-11-10 12:00:00.000000

"""

# revision identifiers, used by Alembic.
revision = 'd2b4f6a8c0e3'
down_revision = ('a1c3e5b7d9f2', 'a9c1e3b5d7f0')
branch_labels = None
depends_on = None


def upgrade():
    # nothing to change: both branches already created their tables
    pass


def downgrade():
    pass
