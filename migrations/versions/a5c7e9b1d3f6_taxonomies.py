"""classifications of the user's own for the holdings, with percentages (F22)

Revision ID: a5c7e9b1d3f6
Revises: f3a5c7e9b1d4
Create Date: 2026-10-13

"""
import sqlalchemy as sa
from alembic import op

revision = 'a5c7e9b1d3f6'
down_revision = 'f3a5c7e9b1d4'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'taxonomies',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.Text(), nullable=False),
        sa.Column('multiple', sa.Boolean(), nullable=False),
        sa.Column('position', sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name'),
    )
    op.create_table(
        'taxonomy_categories',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('taxonomy_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.Text(), nullable=False),
        sa.Column('position', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['taxonomy_id'], ['taxonomies.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('taxonomy_id', 'name'),
    )
    op.create_index(op.f('ix_taxonomy_categories_taxonomy_id'), 'taxonomy_categories', ['taxonomy_id'], unique=False)
    op.create_table(
        'holding_categories',
        sa.Column('holding_id', sa.Integer(), nullable=False),
        sa.Column('category_id', sa.Integer(), nullable=False),
        sa.Column('weight', sa.Numeric(precision=6, scale=2), nullable=False),
        sa.ForeignKeyConstraint(['category_id'], ['taxonomy_categories.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['holding_id'], ['holdings.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('holding_id', 'category_id'),
    )


def downgrade():
    op.drop_table('holding_categories')
    op.drop_index(op.f('ix_taxonomy_categories_taxonomy_id'), table_name='taxonomy_categories')
    op.drop_table('taxonomy_categories')
    op.drop_table('taxonomies')
