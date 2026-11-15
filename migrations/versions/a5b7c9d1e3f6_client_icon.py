"""clients.icon: the icon an archive wears in the selector of the side menu (F98)

Revision ID: a5b7c9d1e3f6
Revises: f4a6c8e0b2d5
Create Date: 2026-11-15 14:00:00.000000

"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = 'a5b7c9d1e3f6'
down_revision = 'f4a6c8e0b2d5'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('clients', schema=None) as batch_op:
        batch_op.add_column(sa.Column('icon', sa.String(length=30), nullable=False, server_default='archive'))


def downgrade():
    with op.batch_alter_table('clients', schema=None) as batch_op:
        batch_op.drop_column('icon')
