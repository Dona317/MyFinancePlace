"""cards: the debit, credit and prepaid cards of an account (F41)

Revision ID: a9c1e3b5d7f0
Revises: f1b3d5a7c9e2
Create Date: 2026-11-02 22:00:00.000000

"""
import sqlalchemy as sa  # noqa: F401 - kept for the revision's imports
from alembic import op  # noqa: F401

# revision identifiers, used by Alembic.
revision = 'a9c1e3b5d7f0'
down_revision = 'f1b3d5a7c9e2'
branch_labels = None
depends_on = None


def upgrade():
    # F41 was first made here with a small table of its own; the table `cards` is now created by f6b8c0d2e4a9
    # (the remote version), so this step does nothing. Kept so that databases which ran it stay on their history.
    pass


def downgrade():
    pass
