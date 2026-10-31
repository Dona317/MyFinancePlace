"""clusters: the group above the category, and the memory rules that set it

The spending model is read on two levels: the cluster (Necessità, Scelte e svago, Risparmio e investimenti)
and, under it, the category. A transaction keeps its cluster; the rules remember the cluster the user chose
for a counterparty or description, so similar transactions get it too.

Revision ID: a7c3e9d1b2f4
Revises: 270b797b5daf
Create Date: 2026-10-16 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a7c3e9d1b2f4'
down_revision = '270b797b5daf'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('transactions', schema=None) as batch_op:
        batch_op.add_column(sa.Column('cluster', sa.String(length=20), nullable=True))

    op.create_table(
        'cluster_rules',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('keyword', sa.Text(), nullable=False),
        sa.Column('cluster', sa.String(length=20), nullable=False),
        sa.Column('source', sa.String(length=10), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('keyword'),
    )


def downgrade():
    op.drop_table('cluster_rules')
    with op.batch_alter_table('transactions', schema=None) as batch_op:
        batch_op.drop_column('cluster')
