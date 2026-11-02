"""studio: groups of archives (a family) and the archive each user opens at sign-in (F21)

Revision ID: b5d7f9a1c3e6
Revises: a3e5c7b9d1f3
Create Date: 2026-10-13

"""
import sqlalchemy as sa
from alembic import op

revision = 'b5d7f9a1c3e6'
down_revision = 'a3e5c7b9d1f3'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'client_groups',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=120), nullable=False),
        sa.Column('color', sa.String(length=7), nullable=False),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_table(
        'client_group_members',
        sa.Column('group_id', sa.Integer(), nullable=False),
        sa.Column('client_id', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['client_id'], ['clients.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['group_id'], ['client_groups.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('group_id', 'client_id'),
    )
    op.add_column('users', sa.Column('default_client_id', sa.Integer(), nullable=True))
    op.create_foreign_key('users_default_client_id_fkey', 'users', 'clients', ['default_client_id'], ['id'],
                          ondelete='SET NULL')


def downgrade():
    op.drop_constraint('users_default_client_id_fkey', 'users', type_='foreignkey')
    op.drop_column('users', 'default_client_id')
    op.drop_table('client_group_members')
    op.drop_table('client_groups')
