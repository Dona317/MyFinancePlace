"""users: sections blocked by an administrator, sections hidden by the user

Revision ID: b1d3f5a7c9e2
Revises: a7c9e1f3b5d6
Create Date: 2026-10-10

"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = 'b1d3f5a7c9e2'
down_revision = 'a7c9e1f3b5d6'
branch_labels = None
depends_on = None


def upgrade():
    for name in ('blocked_sections', 'hidden_sections'):
        op.add_column('users', sa.Column(name, postgresql.ARRAY(sa.String(length=40)), nullable=False,
                                         server_default='{}'))


def downgrade():
    for name in ('hidden_sections', 'blocked_sections'):
        op.drop_column('users', name)
