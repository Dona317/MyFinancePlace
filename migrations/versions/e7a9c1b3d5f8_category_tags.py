"""category tags: the tags a category suggests (F32)

The categories are few and broad (Veicoli, Shopping…); the details are tags suggested by the category (Leasing,
Manutenzione veicolo…), picked with a click when the category is chosen.

Revision ID: e7a9c1b3d5f8
Revises: c9e1a3b5d7f9
Create Date: 2026-11-01 20:00:00.000000

"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'e7a9c1b3d5f8'
down_revision = 'c9e1a3b5d7f9'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('categories', schema=None) as batch_op:
        batch_op.add_column(sa.Column('tags', postgresql.ARRAY(sa.String()), nullable=False, server_default='{}'))


def downgrade():
    with op.batch_alter_table('categories', schema=None) as batch_op:
        batch_op.drop_column('tags')
