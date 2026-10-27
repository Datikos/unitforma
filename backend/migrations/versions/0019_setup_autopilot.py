"""setup autopilot: the solver's settings on the project, its runs, proposed layouts and the
``ai`` kind source (ADR-0025 Decisions 2, 3, 5 and 6)

Expand step. ``projects.setup_auto`` holds the two switches and who turned them on; ``setup_runs``
records every run with its decisions (RLS); ``unit_layouts`` gains ``status`` (confirmed |
proposed), ``source`` (manual | autopilot) and ``match`` (the matcher's figures) so a layout the
solver proposed shares nothing until a person confirms it; ``documents.kind_source`` accepts
``ai`` for a kind the vision classifier set. The previous release ignores the new columns: every
existing layout reads as confirmed and manual, which is what it was.

Revision ID: 0019
Revises: 0018
Create Date: 2026-10-27
"""

from __future__ import annotations

import sys
from pathlib import Path

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from rls import disable_tenant_rls, enable_tenant_rls  # noqa: E402

revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None

_KIND_SOURCES_OLD = "'manual','filename','content','pending'"
_KIND_SOURCES_NEW = _KIND_SOURCES_OLD + ",'ai'"


def upgrade() -> None:
    op.add_column(
        "projects",
        sa.Column("setup_auto", pg.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
    )

    op.create_table(
        "setup_runs",
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
        # queued | running | waiting | done | failed
        sa.Column("status", sa.String(12), nullable=False, server_default="queued"),
        sa.Column("trigger", sa.String(40), nullable=False),
        sa.Column("requested_by", pg.UUID(as_uuid=True)),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("summary", pg.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("error", sa.Text()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "status IN ('queued','running','waiting','done','failed')", name="ck_setup_run_status"
        ),
    )
    op.create_index("ix_setup_runs_tenant_id", "setup_runs", ["tenant_id"])
    op.create_index(
        "ix_setup_runs_project_created",
        "setup_runs",
        ["project_id", sa.text("created_at DESC")],
    )
    enable_tenant_rls("setup_runs")

    op.add_column(
        "unit_layouts",
        sa.Column("status", sa.String(20), nullable=False, server_default="confirmed"),
    )
    op.add_column(
        "unit_layouts",
        sa.Column("source", sa.String(20), nullable=False, server_default="manual"),
    )
    op.add_column("unit_layouts", sa.Column("match", pg.JSONB(), nullable=True))
    op.create_check_constraint(
        "ck_unit_layout_status", "unit_layouts", "status IN ('confirmed','proposed')"
    )
    op.create_check_constraint(
        "ck_unit_layout_source", "unit_layouts", "source IN ('manual','autopilot')"
    )

    op.drop_constraint("ck_document_kind_source", "documents", type_="check")
    op.create_check_constraint(
        "ck_document_kind_source", "documents", f"kind_source IN ({_KIND_SOURCES_NEW})"
    )


def downgrade() -> None:
    # the migration role owns the table and FORCE RLS applies: without the platform scope the
    # UPDATE matches nothing and the constraint below fails on the first ``ai`` row (seen in the
    # CI-style downgrade on 2026-10-27, ADR-0030)
    op.execute("SELECT set_config('app.scope', 'platform', true)")
    op.execute("UPDATE documents SET kind_source = 'manual' WHERE kind_source = 'ai'")
    op.execute("SELECT set_config('app.scope', '', true)")
    op.drop_constraint("ck_document_kind_source", "documents", type_="check")
    op.create_check_constraint(
        "ck_document_kind_source", "documents", f"kind_source IN ({_KIND_SOURCES_OLD})"
    )
    op.drop_constraint("ck_unit_layout_source", "unit_layouts", type_="check")
    op.drop_constraint("ck_unit_layout_status", "unit_layouts", type_="check")
    op.drop_column("unit_layouts", "match")
    op.drop_column("unit_layouts", "source")
    op.drop_column("unit_layouts", "status")
    disable_tenant_rls("setup_runs")
    op.drop_index("ix_setup_runs_project_created", table_name="setup_runs")
    op.drop_index("ix_setup_runs_tenant_id", table_name="setup_runs")
    op.drop_table("setup_runs")
    op.drop_column("projects", "setup_auto")
