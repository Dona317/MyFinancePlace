"""bank_connections, bank_account_links, bank_access_log: PSD2 consents through Enable Banking, the bank accounts they
cover and every access made (F107)

Revision ID: d8e0f2a4b6c9
Revises: c7d9e1f3a5b8
Create Date: 2026-11-21 12:00:00.000000

"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = 'd8e0f2a4b6c9'
down_revision = 'c7d9e1f3a5b8'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'bank_connections',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('provider', sa.String(length=20), nullable=False),
        sa.Column('aspsp_name', sa.String(length=120), nullable=False),
        sa.Column('aspsp_country', sa.String(length=2), nullable=False),
        sa.Column('session_enc', sa.Text(), nullable=True),
        sa.Column('valid_until', sa.DateTime(), nullable=True),
        sa.Column('status', sa.String(length=12), nullable=False),
        sa.Column('last_error', sa.Text(), nullable=True),
        sa.Column('auto_sync', sa.Boolean(), server_default='true', nullable=False),
        sa.Column('auto_save', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_table(
        'bank_account_links',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('connection_id', sa.Integer(), nullable=False),
        sa.Column('uid', sa.String(length=120), nullable=False),
        sa.Column('iban', sa.String(length=34), nullable=True),
        sa.Column('name', sa.Text(), nullable=True),
        sa.Column('currency', sa.String(length=3), nullable=False),
        sa.Column('account_id', sa.Integer(), nullable=True),
        sa.Column('active', sa.Boolean(), server_default='true', nullable=False),
        sa.Column('last_sync_at', sa.DateTime(), nullable=True),
        sa.Column('last_booked', sa.Date(), nullable=True),
        sa.Column('balance', sa.Numeric(precision=38, scale=2), nullable=True),
        sa.Column('balance_date', sa.Date(), nullable=True),
        sa.Column('pending', sa.JSON(), nullable=True),
        sa.Column('skipped', sa.JSON(), nullable=True),
        sa.Column('at_bank', sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(['account_id'], ['accounts.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['connection_id'], ['bank_connections.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('bank_account_links', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_bank_account_links_account_id'), ['account_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_bank_account_links_connection_id'), ['connection_id'], unique=False)
    op.create_table(
        'bank_access_log',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('connection_id', sa.Integer(), nullable=True),
        sa.Column('bank', sa.String(length=120), nullable=False),
        sa.Column('at', sa.DateTime(), nullable=False),
        sa.Column('kind', sa.String(length=10), nullable=False),
        sa.Column('ok', sa.Boolean(), nullable=False),
        sa.Column('saved', sa.Integer(), nullable=False),
        sa.Column('waiting', sa.Integer(), nullable=False),
        sa.Column('at_bank', sa.Integer(), nullable=False),
        sa.Column('message', sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(['connection_id'], ['bank_connections.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('bank_access_log', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_bank_access_log_at'), ['at'], unique=False)
        batch_op.create_index(batch_op.f('ix_bank_access_log_connection_id'), ['connection_id'], unique=False)


def downgrade():
    with op.batch_alter_table('bank_access_log', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_bank_access_log_connection_id'))
        batch_op.drop_index(batch_op.f('ix_bank_access_log_at'))
    op.drop_table('bank_access_log')
    with op.batch_alter_table('bank_account_links', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_bank_account_links_connection_id'))
        batch_op.drop_index(batch_op.f('ix_bank_account_links_account_id'))
    op.drop_table('bank_account_links')
    op.drop_table('bank_connections')
