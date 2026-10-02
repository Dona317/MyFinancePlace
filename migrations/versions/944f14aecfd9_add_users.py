"""add users

Who can sign in. The data stays shared: no other table gets a user column. On the first visit the app asks
to create the first user, an administrator.

Revision ID: 944f14aecfd9
Revises: b7c1d2e3f4a5
Create Date: 2026-09-30 14:51:01.427940

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '944f14aecfd9'
down_revision = 'b7c1d2e3f4a5'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('users',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('username', sa.String(length=80), nullable=False),
    sa.Column('password_hash', sa.String(length=255), nullable=False),
    sa.Column('is_admin', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('last_login', sa.DateTime(), nullable=True),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('username')
    )


def downgrade():
    op.drop_table('users')
