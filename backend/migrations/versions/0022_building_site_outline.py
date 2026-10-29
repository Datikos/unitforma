"""ADR-0035: the site plan's own outline of a placed building

``buildings.site_outline`` holds the closed face of the calibrated site plan that the placed
footprint lands on (site metres), with the sheet, scale and transform it was found for, so a
reader can tell when it is stale. Written by the massing job; ``null`` means "use the hull".
Additive (expand): nullable, compatible with the previous release.

Revision ID: 0022
Revises: 0021
Create Date: 2026-10-29
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0022"
down_revision = "0021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("buildings", sa.Column("site_outline", postgresql.JSONB(), nullable=True))


def downgrade() -> None:
    op.drop_column("buildings", "site_outline")
