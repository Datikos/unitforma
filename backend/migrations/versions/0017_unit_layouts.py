"""unit_layouts: the registry of plan types that owns the media shared by units of one layout
(ADR-0022 Decisions 1 to 4)

Expand step. New table ``unit_layouts`` (RLS); ``units.layout_id``; ``unit_media.layout_id`` with
``unit_id`` made nullable and a check that exactly one owner is set; ``unit_renders.layout_id``.
Backfill: one layout per distinct ``(project_id, lower(attributes->>'layout'))`` of the live
units, then ``units.layout_id``. The previous release keeps reading and writing
``units.attributes.layout``; this release mirrors the code there on every link change (the
contract step is ADR-0022 E1, next release). The previous release always writes ``unit_id`` on
``unit_media``, so its rows satisfy the check.

Revision ID: 0017
Revises: 0016
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

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "unit_layouts",
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
        sa.Column("code", sa.String(40), nullable=False),
        sa.Column("name", sa.String(120)),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_unit_layouts_tenant_id", "unit_layouts", ["tenant_id"])
    op.create_index("ix_unit_layouts_project_id", "unit_layouts", ["project_id"])
    op.execute(
        "CREATE UNIQUE INDEX uq_unit_layouts_project_code ON unit_layouts (project_id, lower(code))"
    )
    enable_tenant_rls("unit_layouts")

    op.add_column(
        "units",
        sa.Column(
            "layout_id",
            pg.UUID(as_uuid=True),
            sa.ForeignKey("unit_layouts.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index("ix_units_layout_id", "units", ["layout_id"])

    op.alter_column("unit_media", "unit_id", existing_type=pg.UUID(as_uuid=True), nullable=True)
    op.add_column(
        "unit_media",
        sa.Column(
            "layout_id",
            pg.UUID(as_uuid=True),
            sa.ForeignKey("unit_layouts.id", ondelete="CASCADE"),
            nullable=True,
        ),
    )
    op.create_index("ix_unit_media_layout_id", "unit_media", ["layout_id"])
    op.create_check_constraint(
        "ck_unit_media_one_owner",
        "unit_media",
        "(unit_id IS NULL) <> (layout_id IS NULL)",
    )

    op.add_column(
        "unit_renders",
        sa.Column(
            "layout_id",
            pg.UUID(as_uuid=True),
            sa.ForeignKey("unit_layouts.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )

    # idempotent backfill under the platform scope (tenant tables force RLS on their owner too)
    op.execute("SELECT set_config('app.scope', 'platform', true)")
    op.execute(
        """
        INSERT INTO unit_layouts (id, tenant_id, project_id, code)
        SELECT gen_random_uuid(), d.tenant_id, d.project_id, d.code
        FROM (
            SELECT DISTINCT ON (u.project_id, lower(u.attributes->>'layout'))
                   u.tenant_id, u.project_id, u.attributes->>'layout' AS code
            FROM units u
            WHERE u.lifecycle_status <> 'removed'
              AND u.attributes ? 'layout'
              AND btrim(u.attributes->>'layout') <> ''
            ORDER BY u.project_id, lower(u.attributes->>'layout'), u.code
        ) d
        ON CONFLICT DO NOTHING
        """
    )
    op.execute(
        """
        UPDATE units u
        SET layout_id = l.id
        FROM unit_layouts l
        WHERE u.layout_id IS NULL
          AND l.project_id = u.project_id
          AND lower(l.code) = lower(u.attributes->>'layout')
        """
    )


def downgrade() -> None:
    op.execute("SELECT set_config('app.scope', 'platform', true)")
    op.drop_column("unit_renders", "layout_id")
    op.drop_constraint("ck_unit_media_one_owner", "unit_media", type_="check")
    op.drop_index("ix_unit_media_layout_id", table_name="unit_media")
    op.drop_column("unit_media", "layout_id")
    op.execute("DELETE FROM unit_media WHERE unit_id IS NULL")
    op.alter_column("unit_media", "unit_id", existing_type=pg.UUID(as_uuid=True), nullable=False)
    op.drop_index("ix_units_layout_id", table_name="units")
    op.drop_column("units", "layout_id")
    disable_tenant_rls("unit_layouts")
    op.execute("DROP INDEX IF EXISTS uq_unit_layouts_project_code")
    op.drop_index("ix_unit_layouts_project_id", table_name="unit_layouts")
    op.drop_index("ix_unit_layouts_tenant_id", table_name="unit_layouts")
    op.drop_table("unit_layouts")
