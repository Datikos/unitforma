"""unit_renders.partner_unit_id: a render of two neighbouring units joined into one apartment,
for viewing and sharing only (ADR-0017 E4)

Additive: one nullable column; the running release never reads it.

Revision ID: 0016
Revises: 0015
Create Date: 2026-10-26
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "unit_renders",
        sa.Column(
            "partner_unit_id",
            pg.UUID(as_uuid=True),
            sa.ForeignKey("units.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("unit_renders", "partner_unit_id")
