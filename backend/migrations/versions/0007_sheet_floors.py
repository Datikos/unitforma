"""sheet_floors: one sheet can show several floors (split-level and multi-block sheets)

A typical sheet of a stepped building shows each block at its own level ("+3.20 / +4.20 /
+5.20" side by side). ``sheet_floors`` holds every (sheet, floor) assignment with an optional
region of the sheet that belongs to that floor. ``sheets.floor_id`` and
``sheets.suggested_floor_id`` stay as the primary assignment for backward compatibility
(expand phase): the services keep them in sync and the next release can drop them.

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-25
"""

from __future__ import annotations

import sys
from pathlib import Path

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from rls import disable_tenant_rls, enable_tenant_rls  # noqa: E402

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "sheet_floors",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            pg.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "sheet_id",
            pg.UUID(as_uuid=True),
            sa.ForeignKey("sheets.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "floor_id",
            pg.UUID(as_uuid=True),
            sa.ForeignKey("floors.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("status", sa.String(20), nullable=False, server_default="confirmed"),
        sa.Column("source", sa.String(20), nullable=False, server_default="manual"),
        # {"ring": [[x, y], ...]} in normalised sheet coordinates; NULL = the whole sheet
        sa.Column("region", pg.JSONB),
        # the level marker that produced a suggestion, e.g. "+3.20"
        sa.Column("marker", sa.String(20)),
        sa.Column("sort_order", sa.Integer, nullable=False, server_default="0"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("sheet_id", "floor_id", name="uq_sheet_floor"),
        sa.CheckConstraint("status IN ('suggested','confirmed')", name="ck_sheet_floor_status"),
    )
    op.create_index("ix_sheet_floors_tenant_id", "sheet_floors", ["tenant_id"])
    op.create_index("ix_sheet_floors_sheet_id", "sheet_floors", ["sheet_id"])
    op.create_index("ix_sheet_floors_floor_id", "sheet_floors", ["floor_id"])
    enable_tenant_rls("sheet_floors")
    op.execute(
        """
        DO $$ BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'app_rw') THEN
            GRANT SELECT, INSERT, UPDATE, DELETE ON sheet_floors TO app_rw;
          END IF;
        END $$;
        """
    )
    # backfill: confirmed assignments, then suggestions on sheets that have none confirmed.
    # The migration role owns the table; FORCE RLS needs the platform scope for this copy.
    op.execute("SELECT set_config('app.scope', 'platform', true)")
    op.execute(
        """
        INSERT INTO sheet_floors (id, tenant_id, sheet_id, floor_id, status, source)
        SELECT gen_random_uuid(), s.tenant_id, s.id, s.floor_id, 'confirmed', 'legacy'
          FROM sheets s JOIN floors f ON f.id = s.floor_id
        """
    )
    op.execute(
        """
        INSERT INTO sheet_floors (id, tenant_id, sheet_id, floor_id, status, source)
        SELECT gen_random_uuid(), s.tenant_id, s.id, s.suggested_floor_id, 'suggested', 'legacy'
          FROM sheets s JOIN floors f ON f.id = s.suggested_floor_id
         WHERE s.floor_id IS NULL
        """
    )
    op.execute("SELECT set_config('app.scope', '', true)")


def downgrade() -> None:
    disable_tenant_rls("sheet_floors")
    op.drop_table("sheet_floors")
