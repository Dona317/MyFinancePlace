"""subcategories

A category can belong to a main category (Bollette → Luce), one level only. Transactions keep storing one
name, the most specific; totals are grouped by main category where the overview matters.

Revision ID: 270b797b5daf
Revises: d015a2d4e37c
Create Date: 2026-09-30 22:14:02.213368

"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = '270b797b5daf'
down_revision = 'd015a2d4e37c'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('categories', schema=None) as batch_op:
        batch_op.add_column(sa.Column('parent_id', sa.Integer(), nullable=True))
        batch_op.create_index(batch_op.f('ix_categories_parent_id'), ['parent_id'], unique=False)
        batch_op.create_foreign_key('categories_parent_id_fkey', 'categories', ['parent_id'], ['id'], ondelete='SET NULL')



def downgrade():
    with op.batch_alter_table('categories', schema=None) as batch_op:
        batch_op.drop_constraint('categories_parent_id_fkey', type_='foreignkey')
        batch_op.drop_index(batch_op.f('ix_categories_parent_id'))
        batch_op.drop_column('parent_id')

