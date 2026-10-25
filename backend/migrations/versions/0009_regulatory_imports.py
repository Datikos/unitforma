"""regulatory_imports: permit records pulled from a public registry (ADR-0007)

One row per fetch of a building permit (today: Tbilisi Architecture Service, ``source =
'tasge'``). ``record`` is the normalised, personal-data-free shape of the permit; ``stats`` counts
the attachments imported, skipped and failed by the worker. ``projects.regulatory`` keeps only a
summary so project reads stay small. Additive; nothing existing changes.

Revision ID: 0009
Revises: 0008
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

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "regulatory_imports",
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
        sa.Column("source", sa.String(20), nullable=False),
        sa.Column("external_id", sa.String(40), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="fetched"),
        sa.Column("requested_by", pg.UUID(as_uuid=True)),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("record", pg.JSONB, nullable=False, server_default="{}"),
        sa.Column("stats", pg.JSONB, nullable=False, server_default="{}"),
        sa.Column("error", sa.Text),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "status IN ('fetched','importing','done','failed')", name="ck_regulatory_import_status"
        ),
    )
    op.create_index("ix_regulatory_imports_tenant_id", "regulatory_imports", ["tenant_id"])
    op.create_index("ix_regulatory_imports_project_id", "regulatory_imports", ["project_id"])
    enable_tenant_rls("regulatory_imports")
    op.execute(
        """
        DO $$ BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'app_rw') THEN
            GRANT SELECT, INSERT, UPDATE, DELETE ON regulatory_imports TO app_rw;
          END IF;
        END $$;
        """
    )


def downgrade() -> None:
    disable_tenant_rls("regulatory_imports")
    op.drop_table("regulatory_imports")
