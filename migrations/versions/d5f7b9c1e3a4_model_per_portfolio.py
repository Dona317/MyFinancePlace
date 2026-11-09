"""portfolio_templates.portfolio_id: one model portfolio per portfolio (F50)

Revision ID: d5f7b9c1e3a4
Revises: c4e6a8b0d2f3
Create Date: 2026-11-09

"""
import sqlalchemy as sa
from alembic import op

revision = 'd5f7b9c1e3a4'
down_revision = 'c4e6a8b0d2f3'
branch_labels = None
depends_on = None


def upgrade():
    # empty for the models there are: they keep looking at all the investments together
    op.add_column('portfolio_templates', sa.Column('portfolio_id', sa.Integer(),
                                                   sa.ForeignKey('portfolios.id', ondelete='SET NULL')))
    op.create_index('ix_portfolio_templates_portfolio_id', 'portfolio_templates', ['portfolio_id'])


def downgrade():
    op.drop_index('ix_portfolio_templates_portfolio_id', table_name='portfolio_templates')
    op.drop_column('portfolio_templates', 'portfolio_id')
