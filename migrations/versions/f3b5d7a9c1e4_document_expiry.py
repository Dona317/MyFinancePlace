"""warranties and expiring documents (F23)

Revision ID: f3b5d7a9c1e4
Revises: d1f3a5c7e9b2
Create Date: 2026-10-19

"""
import sqlalchemy as sa
from alembic import op

revision = 'f3b5d7a9c1e4'
down_revision = 'd1f3a5c7e9b2'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('documents') as batch:
        batch.add_column(sa.Column('subject', sa.Text(), nullable=True))
        batch.add_column(sa.Column('expires_on', sa.Date(), nullable=True))
        batch.add_column(sa.Column('warranty_until', sa.Date(), nullable=True))


def downgrade():
    with op.batch_alter_table('documents') as batch:
        batch.drop_column('warranty_until')
        batch.drop_column('expires_on')
        batch.drop_column('subject')
