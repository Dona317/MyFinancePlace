"""add app_settings and duplicate_dismissals

Revision ID: c7d2e9f1a3b4
Revises: b3f1c2d4e5a6
Create Date: 2026-09-25 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c7d2e9f1a3b4'
down_revision = 'b3f1c2d4e5a6'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'app_settings',
        sa.Column('key', sa.String(length=100), nullable=False),
        sa.Column('value', sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint('key'),
    )
    op.create_table(
        'duplicate_dismissals',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('first_id', sa.Integer(), nullable=False),
        sa.Column('second_id', sa.Integer(), nullable=False),
        sa.CheckConstraint('first_id < second_id', name='ck_duplicate_dismissals_ordered'),
        sa.ForeignKeyConstraint(['first_id'], ['transactions.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['second_id'], ['transactions.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('first_id', 'second_id'),
    )


def downgrade():
    op.drop_table('duplicate_dismissals')
    op.drop_table('app_settings')
