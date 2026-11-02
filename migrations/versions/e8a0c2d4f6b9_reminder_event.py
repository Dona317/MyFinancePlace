"""reminder event: a reminder and its spending event, tied both ways (F33)

Revision ID: e8a0c2d4f6b9
Revises: d6f8b0c2e4a7
Create Date: 2026-11-02 19:00:00.000000

"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = 'e8a0c2d4f6b9'
down_revision = 'd6f8b0c2e4a7'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('reminders', schema=None) as batch_op:
        batch_op.add_column(sa.Column('event_id', sa.Integer(), nullable=True))
        batch_op.create_index('ix_reminders_event_id', ['event_id'], unique=False)
        batch_op.create_foreign_key('fk_reminders_event_id', 'spending_events', ['event_id'], ['id'], ondelete='SET NULL')


def downgrade():
    with op.batch_alter_table('reminders', schema=None) as batch_op:
        batch_op.drop_constraint('fk_reminders_event_id', type_='foreignkey')
        batch_op.drop_index('ix_reminders_event_id')
        batch_op.drop_column('event_id')
