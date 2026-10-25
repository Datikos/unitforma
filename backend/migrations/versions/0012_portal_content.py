"""portal_content: entrance on units; construction status, completion, terms and elevation sheet on
buildings; entrance in the portal read model (ADR-0014 Decision 6)

Everything is nullable and additive: the running release ignores the new columns, the next one reads
them. ``elevation_sheet_id`` points at the sheet whose stacked level markers give the portal's
elevation floor picker (ADR-0014 Decision 1) and is cleared when the sheet goes.

Revision ID: 0012
Revises: 0011
Create Date: 2026-10-26
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("units", sa.Column("entrance", sa.String(20), nullable=True))
    op.add_column("buildings", sa.Column("construction_status", sa.String(20), nullable=True))
    op.add_column("buildings", sa.Column("completion", sa.String(80), nullable=True))
    op.add_column("buildings", sa.Column("terms", sa.Text(), nullable=True))
    op.add_column(
        "buildings",
        sa.Column(
            "elevation_sheet_id",
            pg.UUID(as_uuid=True),
            sa.ForeignKey("sheets.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_check_constraint(
        "ck_building_construction_status",
        "buildings",
        "construction_status IS NULL OR construction_status IN "
        "('planned','under_construction','completed')",
    )
    op.add_column("published_units", sa.Column("entrance", sa.String(20), nullable=True))


def downgrade() -> None:
    op.drop_column("published_units", "entrance")
    op.drop_constraint("ck_building_construction_status", "buildings", type_="check")
    op.drop_column("buildings", "elevation_sheet_id")
    op.drop_column("buildings", "terms")
    op.drop_column("buildings", "completion")
    op.drop_column("buildings", "construction_status")
    op.drop_column("units", "entrance")
