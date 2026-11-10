"""holding_exposures: what a fund holds by country, sector, currency, company and asset class — read from the
issuer's holdings file or typed by hand (F57, services.lookthrough)

Revision ID: a1c3e5b7d9f2
Revises: f7b9d1e3a5c6
Create Date: 2026-11-10

"""
import sqlalchemy as sa
from alembic import op

revision = 'a1c3e5b7d9f2'
down_revision = 'f7b9d1e3a5c6'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'holding_exposures',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('holding_id', sa.Integer(), nullable=False),
        sa.Column('kind', sa.String(length=20), nullable=False),
        sa.Column('name', sa.Text(), nullable=False),
        sa.Column('weight', sa.Numeric(9, 4), nullable=False),
        sa.Column('as_of', sa.Date(), nullable=False),
        sa.Column('source', sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(['holding_id'], ['holdings.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('holding_id', 'kind', 'name'),
    )
    op.create_index(op.f('ix_holding_exposures_holding_id'), 'holding_exposures', ['holding_id'], unique=False)


def downgrade():
    op.drop_index(op.f('ix_holding_exposures_holding_id'), table_name='holding_exposures')
    op.drop_table('holding_exposures')
