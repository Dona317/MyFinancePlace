"""instrument «Fondo» → «Fondo comune» (next to the new «Fondo assicurativo»); asset classes «Bilanciato» → «Misto»,
«Materie prime» → «Commodities» (F70)

Revision ID: c4e6a8b0d2f3
Revises: b3d5f7a9c1e2
Create Date: 2026-11-09

"""
from alembic import op

revision = 'c4e6a8b0d2f3'
down_revision = 'b3d5f7a9c1e2'
branch_labels = None
depends_on = None


def upgrade():
    op.execute("UPDATE holdings SET asset_class = 'Fondo comune' WHERE asset_class = 'Fondo'")
    op.execute("UPDATE template_slots SET asset_class = 'Fondo comune' WHERE asset_class = 'Fondo'")
    op.execute("UPDATE holdings SET allocation_class = 'Misto' WHERE allocation_class = 'Bilanciato'")
    op.execute("UPDATE holdings SET allocation_class = 'Commodities' WHERE allocation_class = 'Materie prime'")


def downgrade():
    op.execute("UPDATE holdings SET asset_class = 'Fondo' WHERE asset_class = 'Fondo comune'")
    op.execute("UPDATE template_slots SET asset_class = 'Fondo' WHERE asset_class = 'Fondo comune'")
    op.execute("UPDATE holdings SET allocation_class = 'Bilanciato' WHERE allocation_class = 'Misto'")
    op.execute("UPDATE holdings SET allocation_class = 'Materie prime' WHERE allocation_class = 'Commodities'")
