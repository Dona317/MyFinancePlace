"""counterparty shown as a tag; AI tag renamed

Data only. The counterparty is no longer a field of its own in the app: it becomes the first tag of the
transaction (the column stays, for the rules, the search and the AI). The tag "categoria-ai" (category
suggested by the AI and accepted unchanged) becomes "da confermare (AI)".

Revision ID: b7c1d2e3f4a5
Revises: f9a61d256bab
Create Date: 2026-09-30 13:40:00

"""
from alembic import op


# revision identifiers, used by Alembic.
revision = 'b7c1d2e3f4a5'
down_revision = 'f9a61d256bab'
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        UPDATE transactions
        SET tags = array_replace(tags, 'categoria-ai', 'da confermare (AI)')
        WHERE 'categoria-ai' = ANY(tags)
    """)
    # the counterparty first, unless a tag with the same name (any case) is already there
    op.execute("""
        UPDATE transactions
        SET tags = ARRAY[btrim(counterparty)]::varchar[] || COALESCE(tags, ARRAY[]::varchar[])
        WHERE counterparty IS NOT NULL AND btrim(counterparty) <> ''
          AND NOT EXISTS (SELECT 1 FROM unnest(COALESCE(tags, ARRAY[]::varchar[])) AS t(tag)
                          WHERE lower(t.tag) = lower(btrim(counterparty)))
    """)


def downgrade():
    # the counterparty column was never touched: only the AI tag name goes back
    op.execute("""
        UPDATE transactions
        SET tags = array_replace(tags, 'da confermare (AI)', 'categoria-ai')
        WHERE 'da confermare (AI)' = ANY(tags)
    """)
