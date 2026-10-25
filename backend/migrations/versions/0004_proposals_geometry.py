"""revision diff proposals and generated geometry models

Revision ID: 0004
Revises: 0003
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

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None

TENANT_TABLES = ["mapping_proposals", "mapping_proposal_items", "geometry_models"]


def _id():
    return sa.Column("id", pg.UUID(as_uuid=True), primary_key=True)


def _tenant():
    return sa.Column(
        "tenant_id",
        pg.UUID(as_uuid=True),
        sa.ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
    )


def _fk(name, table, ondelete="CASCADE", nullable=False):
    return sa.Column(
        name,
        pg.UUID(as_uuid=True),
        sa.ForeignKey(f"{table}.id", ondelete=ondelete),
        nullable=nullable,
    )


def _ts():
    return [
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    ]


def upgrade() -> None:
    op.create_table(
        "mapping_proposals",
        _id(),
        _tenant(),
        _fk("project_id", "projects"),
        _fk("document_id", "documents"),
        sa.Column("old_revision_id", pg.UUID(as_uuid=True)),
        _fk("new_revision_id", "document_revisions"),
        sa.Column("status", sa.String(20), nullable=False, server_default="open"),
        sa.Column("summary", pg.JSONB, nullable=False, server_default="{}"),
        sa.Column("created_by", pg.UUID(as_uuid=True)),
        sa.Column("resolved_at", sa.DateTime(timezone=True)),
        *_ts(),
        sa.CheckConstraint("status IN ('open','resolved','dismissed')", name="ck_proposal_status"),
    )
    for col in ("tenant_id", "project_id", "document_id", "new_revision_id"):
        op.create_index(f"ix_mapping_proposals_{col}", "mapping_proposals", [col])

    op.create_table(
        "mapping_proposal_items",
        _id(),
        _tenant(),
        _fk("proposal_id", "mapping_proposals"),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column(
            "old_unit_ids", pg.ARRAY(pg.UUID(as_uuid=True)), nullable=False, server_default="{}"
        ),
        sa.Column(
            "old_boundary_ids",
            pg.ARRAY(pg.UUID(as_uuid=True)),
            nullable=False,
            server_default="{}",
        ),
        sa.Column("old_sheet_id", pg.UUID(as_uuid=True)),
        _fk("new_sheet_id", "sheets", "SET NULL", True),
        sa.Column("new_rings", pg.JSONB, nullable=False, server_default="[]"),
        sa.Column("labels", pg.JSONB, nullable=False, server_default="[]"),
        sa.Column("overlaps", pg.JSONB, nullable=False, server_default="[]"),
        sa.Column("confidence", sa.Numeric(4, 3), nullable=False, server_default="0"),
        sa.Column("decision", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("decided_by", pg.UUID(as_uuid=True)),
        sa.Column("decided_at", sa.DateTime(timezone=True)),
        sa.Column("result", pg.JSONB, nullable=False, server_default="{}"),
        *_ts(),
        sa.CheckConstraint(
            "kind IN ('matched','relabelled','split','merged','new','missing','complex')",
            name="ck_proposal_item_kind",
        ),
        sa.CheckConstraint(
            "decision IN ('pending','accepted','rejected')", name="ck_proposal_item_decision"
        ),
    )
    op.create_index("ix_mapping_proposal_items_tenant_id", "mapping_proposal_items", ["tenant_id"])
    op.create_index(
        "ix_mapping_proposal_items_proposal_id", "mapping_proposal_items", ["proposal_id"]
    )

    op.create_table(
        "geometry_models",
        _id(),
        _tenant(),
        _fk("project_id", "projects"),
        _fk("building_id", "buildings", "SET NULL", True),
        sa.Column("kind", sa.String(30), nullable=False),
        sa.Column("revision_id", pg.UUID(as_uuid=True)),
        sa.Column("glb_key", sa.String(512)),
        sa.Column("model_transform", pg.JSONB, nullable=False, server_default="{}"),
        sa.Column("units_scale", sa.Numeric(10, 6), nullable=False, server_default="1"),
        sa.Column("status", sa.String(20), nullable=False, server_default="generating"),
        sa.Column("stats", pg.JSONB, nullable=False, server_default="{}"),
        sa.Column("error", sa.Text),
        sa.Column("is_current", sa.Boolean, nullable=False, server_default=sa.true()),
        *_ts(),
        sa.CheckConstraint(
            "kind IN ('massing_generated','glb_source','ifc')", name="ck_geometry_kind"
        ),
        sa.CheckConstraint("status IN ('generating','ready','failed')", name="ck_geometry_status"),
    )
    op.create_index("ix_geometry_models_tenant_id", "geometry_models", ["tenant_id"])
    op.create_index("ix_geometry_models_project_id", "geometry_models", ["project_id"])
    op.create_index(
        "ix_geometry_models_project_current",
        "geometry_models",
        ["project_id", "kind"],
        postgresql_where=sa.text("is_current"),
    )

    for t in TENANT_TABLES:
        enable_tenant_rls(t)
    op.execute(
        """
        DO $$ BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'app_rw') THEN
            GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO app_rw;
          END IF;
        END $$;
        """
    )


def downgrade() -> None:
    for t in TENANT_TABLES:
        disable_tenant_rls(t)
    for t in ["geometry_models", "mapping_proposal_items", "mapping_proposals"]:
        op.drop_table(t)
