"""category nature: fixed / periodic / variable spending

Revision ID: b2d4f6a8c0e1
Revises: a1c2e3f4b5d6
Create Date: 2026-10-07

"""
import sqlalchemy as sa
from alembic import op

revision = 'b2d4f6a8c0e1'
down_revision = 'a1c2e3f4b5d6'
branch_labels = None
depends_on = None

# The default categories' nature (app/services/categories.py NATURE_DEFAULTS, copied: a migration does not import the app)
FIXED = ("Casa", "Affitto", "Mutuo", "Condominio", "Bollette", "Luce", "Gas", "Acqua", "Internet e telefono", "Prestiti",
         "Abbonamenti", "Streaming", "Software", "Palestra", "Commissioni")
PERIODIC = ("Manutenzione", "Auto", "Macchina", "Assicurazioni", "Tasse e imposte", "Istruzione", "Viaggi",
            "Regali e donazioni", "Gift")


def upgrade():
    op.add_column('categories', sa.Column('nature', sa.String(length=10), nullable=True))
    categories = sa.table('categories', sa.column('name', sa.Text), sa.column('kind', sa.String),
                          sa.column('nature', sa.String))
    for nature, names in (("fixed", FIXED), ("periodic", PERIODIC)):
        op.execute(categories.update().where(categories.c.name.in_(names), categories.c.kind != "income")
                   .values(nature=nature))


def downgrade():
    op.drop_column('categories', 'nature')
