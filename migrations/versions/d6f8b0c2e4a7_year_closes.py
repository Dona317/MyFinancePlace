"""year closes: the three statements of a year saved on 1 January, again when its transactions change

Revision ID: d6f8b0c2e4a7
Revises: c4e6a8b0d2f5
Create Date: 2026-11-02 17:00:00.000000

"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = 'd6f8b0c2e4a7'
down_revision = 'c4e6a8b0d2f5'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'year_closes',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('year', sa.Integer(), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('closed_at', sa.DateTime(), nullable=False),
        sa.Column('automatic', sa.Boolean(), nullable=False),
        sa.Column('fingerprint', sa.String(length=32), nullable=False),
        sa.Column('data', sa.JSON(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('year', 'version', name='uq_year_closes_year_version'),
    )
    with op.batch_alter_table('year_closes', schema=None) as batch_op:
        batch_op.create_index('ix_year_closes_year', ['year'], unique=False)


def downgrade():
    with op.batch_alter_table('year_closes', schema=None) as batch_op:
        batch_op.drop_index('ix_year_closes_year')
    op.drop_table('year_closes')
