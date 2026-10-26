"""unit_renders: AI-generated 3D plan renders requested by staff and reviewed before they become
unit media (ADR-0017 Decision 3)

Additive: a new table with the standard tenant RLS policies; the running release never reads it.
The image itself is a ``unit_media`` row (private until approved); this table keeps the request,
its prompt, the plan crop that was sent, the outcome and who reviewed it.

Revision ID: 0014
Revises: 0013
Create Date: 2026-10-26
"""

from __future__ import annotations

import sys
from pathlib import Path

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from rls import disable_tenant_rls, enable_tenant_rls  # noqa: E402

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "unit_renders",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            pg.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "project_id",
            pg.UUID(as_uuid=True),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "unit_id",
            pg.UUID(as_uuid=True),
            sa.ForeignKey("units.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("status", sa.String(12), nullable=False, server_default="queued"),
        sa.Column("provider", sa.String(20), nullable=False),
        sa.Column("model", sa.String(80), nullable=False),
        sa.Column("prompt", sa.Text(), nullable=False),
        sa.Column("note", sa.String(500), nullable=True),
        sa.Column("input_key", sa.String(512), nullable=True),
        sa.Column(
            "media_id",
            pg.UUID(as_uuid=True),
            sa.ForeignKey("unit_media.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("cost_usd", sa.Numeric(8, 4), nullable=True),
        sa.Column("requested_by", pg.UUID(as_uuid=True), nullable=True),
        sa.Column("reviewed_by", pg.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'review', 'approved', 'rejected', 'failed')",
            name="ck_unit_render_status",
        ),
    )
    op.create_index("ix_unit_renders_unit_created", "unit_renders", ["unit_id", "created_at"])
    op.create_index("ix_unit_renders_tenant_created", "unit_renders", ["tenant_id", "created_at"])
    enable_tenant_rls("unit_renders")


def downgrade() -> None:
    disable_tenant_rls("unit_renders")
    op.drop_index("ix_unit_renders_tenant_created", table_name="unit_renders")
    op.drop_index("ix_unit_renders_unit_created", table_name="unit_renders")
    op.drop_table("unit_renders")
