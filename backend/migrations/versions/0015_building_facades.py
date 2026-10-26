"""buildings.facades: the facade drawings assigned to a building's sides move from
``projects.site_frame.facades[building_id]`` into their own column (ADR-0016 E3)

Expand step: a nullable JSONB column ``{"v": 1, "items": [{side, sheet_id, region, flip}]}``,
backfilled from the site frame where the previous release stored it. The previous release keeps
working: it reads and writes the site-frame key, which this release mirrors on every write and
reads when the column is still null. The contract step (stop mirroring, drop the key) is the
next release.

Revision ID: 0015
Revises: 0014
Create Date: 2026-10-26
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("buildings", sa.Column("facades", pg.JSONB(astext_type=sa.Text()), nullable=True))
    # idempotent backfill: only buildings without a column value and with a legacy entry. The
    # tenant tables force row-level security on their owner too, so the migration's transaction
    # takes the platform scope first or the UPDATE matches nothing.
    op.execute("SELECT set_config('app.scope', 'platform', true)")
    op.execute(
        """
        UPDATE buildings b
        SET facades = jsonb_build_object('v', 1, 'items', p.site_frame->'facades'->(b.id::text))
        FROM projects p
        WHERE p.id = b.project_id
          AND b.facades IS NULL
          AND jsonb_typeof(p.site_frame->'facades') = 'object'
          AND (p.site_frame->'facades') ? (b.id::text)
        """
    )


def downgrade() -> None:
    op.drop_column("buildings", "facades")
