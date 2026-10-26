"""published_units.layout: the plan-type code on the portal read model, so the units list filters
by layout and the plan-types page counts live from one grouped query (ADR-0024 Decision 2)

Expand step: one nullable column, backfilled from the unit document's ``layout`` key so the live
publication serves the filter without a republish. The previous release never reads it.

Revision ID: 0018
Revises: 0017
Create Date: 2026-10-27
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("published_units", sa.Column("layout", sa.String(40), nullable=True))
    # tenant tables force RLS on their owner too: take the platform scope or the UPDATE is a no-op
    op.execute("SELECT set_config('app.scope', 'platform', true)")
    op.execute(
        """
        UPDATE published_units
        SET layout = left(data->>'layout', 40)
        WHERE layout IS NULL AND data ? 'layout' AND btrim(data->>'layout') <> ''
        """
    )


def downgrade() -> None:
    op.drop_column("published_units", "layout")
