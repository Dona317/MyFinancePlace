"""reminders.account_id: the reminder to reconcile an account again, made after a reconciliation (T11)

Revision ID: c7d9e1f3a5b8
Revises: b6c8d0e2f4a7
Create Date: 2026-11-16 23:30:00.000000

"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = 'c7d9e1f3a5b8'
down_revision = 'b6c8d0e2f4a7'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('reminders', schema=None) as batch_op:
        batch_op.add_column(sa.Column('account_id', sa.Integer(), nullable=True))
        batch_op.create_index(batch_op.f('ix_reminders_account_id'), ['account_id'], unique=False)
        batch_op.create_foreign_key('fk_reminders_account_id', 'accounts', ['account_id'], ['id'], ondelete='SET NULL')


def downgrade():
    with op.batch_alter_table('reminders', schema=None) as batch_op:
        batch_op.drop_constraint('fk_reminders_account_id', type_='foreignkey')
        batch_op.drop_index(batch_op.f('ix_reminders_account_id'))
        batch_op.drop_column('account_id')
