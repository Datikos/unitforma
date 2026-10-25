"""sheet exclusion and printed areas on revision-diff items

A drawing set often bundles reprints of the floor plans (fire-safety, egress, accessibility
sets), details and schedules with the architectural plans. ``sheets.excluded`` takes a page out
of mapping (no floors, no suggestions, no units) with a reason; ``mapping_proposal_items.
printed_areas`` carries the area printed next to each new outline's label so accepting an
item updates the unit's documented area (plan §13.2 "Areas"). Both columns are additive.

Revision ID: 0008
Revises: 0007
Create Date: 2026-10-25
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "sheets", sa.Column("excluded", sa.Boolean, nullable=False, server_default=sa.false())
    )
    op.add_column("sheets", sa.Column("exclusion_reason", sa.String(200)))
    op.add_column("mapping_proposal_items", sa.Column("printed_areas", pg.JSONB))


def downgrade() -> None:
    op.drop_column("mapping_proposal_items", "printed_areas")
    op.drop_column("sheets", "exclusion_reason")
    op.drop_column("sheets", "excluded")
