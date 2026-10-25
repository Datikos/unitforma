"""documents, revisions, sheets, units, boundaries, lineage, areas

Revision ID: 0003
Revises: 0002
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

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

TENANT_TABLES = [
    "documents",
    "document_revisions",
    "sheets",
    "units",
    "unit_code_history",
    "unit_boundaries",
    "unit_lineage_events",
    "unit_areas",
]


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


def _version():
    return sa.Column("version", sa.Integer, nullable=False, server_default="1")


def upgrade() -> None:
    op.create_table(
        "documents",
        _id(),
        _tenant(),
        _fk("project_id", "projects"),
        _fk("building_id", "buildings", "SET NULL", True),
        sa.Column("kind", sa.String(30), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("visibility", sa.String(20), nullable=False, server_default="internal"),
        sa.Column("current_revision_id", pg.UUID(as_uuid=True)),
        sa.Column("source", pg.JSONB, nullable=False, server_default="{}"),
        *_ts(),
        sa.CheckConstraint(
            "kind IN ('site_plan','floor_plan','section','elevation','render','schedule',"
            "'model_ifc','model_glb','texture','permit','other')",
            name="ck_document_kind",
        ),
    )
    op.create_index("ix_documents_tenant_id", "documents", ["tenant_id"])
    op.create_index("ix_documents_project_id", "documents", ["project_id"])

    op.create_table(
        "document_revisions",
        _id(),
        _tenant(),
        _fk("document_id", "documents"),
        sa.Column("revision_no", sa.Integer, nullable=False),
        sa.Column("object_key", sa.String(512), nullable=False),
        sa.Column("file_name", sa.String(255), nullable=False),
        sa.Column("mime", sa.String(120)),
        sa.Column("byte_size", sa.BigInteger),
        sa.Column("sha256", sa.String(64)),
        sa.Column("page_count", sa.Integer),
        sa.Column("uploaded_by", pg.UUID(as_uuid=True)),
        sa.Column("source_note", sa.Text),
        sa.Column("processing_status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("processing_error", sa.Text),
        sa.Column("supersedes_revision_id", pg.UUID(as_uuid=True)),
        *_ts(),
        sa.UniqueConstraint("document_id", "revision_no", name="uq_revision_no"),
    )
    op.create_index("ix_document_revisions_tenant_id", "document_revisions", ["tenant_id"])
    op.create_index("ix_document_revisions_document_id", "document_revisions", ["document_id"])

    op.create_table(
        "sheets",
        _id(),
        _tenant(),
        _fk("revision_id", "document_revisions"),
        sa.Column("page_no", sa.Integer, nullable=False),
        sa.Column("width_pt", sa.Numeric(10, 3)),
        sa.Column("height_pt", sa.Numeric(10, 3)),
        sa.Column("raster_key", sa.String(512)),
        sa.Column("raster_width", sa.Integer),
        sa.Column("raster_height", sa.Integer),
        sa.Column("thumbnail_key", sa.String(512)),
        sa.Column("extract_key", sa.String(512)),
        _fk("floor_id", "floors", "SET NULL", True),
        sa.Column("suggested_floor_id", pg.UUID(as_uuid=True)),
        sa.Column("assignment_status", sa.String(20), nullable=False, server_default="unassigned"),
        sa.Column("calibration", pg.JSONB),
        sa.Column("calibration_status", sa.String(20), nullable=False, server_default="none"),
        sa.Column("hints", pg.JSONB, nullable=False, server_default="{}"),
        _version(),
        *_ts(),
        sa.UniqueConstraint("revision_id", "page_no", name="uq_sheet_page"),
    )
    op.create_index("ix_sheets_tenant_id", "sheets", ["tenant_id"])
    op.create_index("ix_sheets_revision_id", "sheets", ["revision_id"])
    op.create_index("ix_sheets_floor_id", "sheets", ["floor_id"])

    op.create_table(
        "units",
        _id(),
        _tenant(),
        _fk("project_id", "projects"),
        _fk("building_id", "buildings", "RESTRICT"),
        _fk("floor_id", "floors", "RESTRICT"),
        sa.Column("code", sa.String(40), nullable=False),
        sa.Column("unit_type", sa.String(20), nullable=False, server_default="apartment"),
        sa.Column("lifecycle_status", sa.String(20), nullable=False, server_default="draft"),
        sa.Column(
            "verification_status", sa.String(20), nullable=False, server_default="unverified"
        ),
        sa.Column(
            "publication_status", sa.String(20), nullable=False, server_default="unpublished"
        ),
        sa.Column("created_from_revision_id", pg.UUID(as_uuid=True)),
        sa.Column("removed_by_revision_id", pg.UUID(as_uuid=True)),
        sa.Column("rooms", sa.Integer),
        sa.Column("bedrooms", sa.Integer),
        sa.Column("bathrooms", sa.Integer),
        sa.Column("orientation", sa.String(20)),
        sa.Column("attributes", pg.JSONB, nullable=False, server_default="{}"),
        _version(),
        *_ts(),
        sa.CheckConstraint(
            "unit_type IN ('apartment','commercial','parking','storage')", name="ck_unit_type"
        ),
        sa.CheckConstraint(
            "lifecycle_status IN ('draft','active','removed')", name="ck_unit_lifecycle"
        ),
        sa.CheckConstraint(
            "verification_status IN ('unverified','in_review','verified')",
            name="ck_unit_verification",
        ),
        sa.CheckConstraint(
            "publication_status IN ('unpublished','published','hidden')", name="ck_unit_publication"
        ),
    )
    op.create_index("ix_units_tenant_id", "units", ["tenant_id"])
    op.create_index("ix_units_project_id", "units", ["project_id"])
    op.create_index("ix_units_building_id", "units", ["building_id"])
    op.create_index("ix_units_floor_id", "units", ["floor_id"])
    # readable codes are unique among non-removed units of a project (plan §5.4)
    op.execute(
        "CREATE UNIQUE INDEX uq_units_project_code_live ON units (project_id, lower(code)) "
        "WHERE lifecycle_status <> 'removed'"
    )

    op.create_table(
        "unit_code_history",
        _id(),
        _tenant(),
        _fk("unit_id", "units"),
        sa.Column("old_code", sa.String(40)),
        sa.Column("new_code", sa.String(40), nullable=False),
        sa.Column("changed_by", pg.UUID(as_uuid=True)),
        sa.Column("revision_id", pg.UUID(as_uuid=True)),
        sa.Column("reason", sa.Text),
        sa.Column(
            "changed_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_unit_code_history_tenant_id", "unit_code_history", ["tenant_id"])
    op.create_index("ix_unit_code_history_unit_id", "unit_code_history", ["unit_id"])

    op.create_table(
        "unit_boundaries",
        _id(),
        _tenant(),
        _fk("unit_id", "units"),
        _fk("sheet_id", "sheets"),
        sa.Column("polygon", pg.JSONB, nullable=False),
        sa.Column("polygon_m", pg.JSONB),
        sa.Column("source", sa.String(20), nullable=False, server_default="manual"),
        sa.Column("status", sa.String(20), nullable=False, server_default="draft"),
        sa.Column("is_current", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("label", sa.String(80)),
        sa.Column("approved_by", pg.UUID(as_uuid=True)),
        sa.Column("approved_at", sa.DateTime(timezone=True)),
        _version(),
        *_ts(),
        sa.CheckConstraint(
            "status IN ('draft','approved','superseded')", name="ck_boundary_status"
        ),
    )
    op.create_index("ix_unit_boundaries_tenant_id", "unit_boundaries", ["tenant_id"])
    op.create_index("ix_unit_boundaries_unit_id", "unit_boundaries", ["unit_id"])
    op.create_index(
        "ix_unit_boundaries_sheet_current",
        "unit_boundaries",
        ["sheet_id"],
        postgresql_where=sa.text("is_current"),
    )

    op.create_table(
        "unit_lineage_events",
        _id(),
        _tenant(),
        _fk("project_id", "projects"),
        sa.Column("event_type", sa.String(30), nullable=False),
        sa.Column("revision_id", pg.UUID(as_uuid=True)),
        sa.Column(
            "from_unit_ids", pg.ARRAY(pg.UUID(as_uuid=True)), nullable=False, server_default="{}"
        ),
        sa.Column(
            "to_unit_ids", pg.ARRAY(pg.UUID(as_uuid=True)), nullable=False, server_default="{}"
        ),
        sa.Column("decided_by", pg.UUID(as_uuid=True)),
        sa.Column(
            "decided_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("note", sa.Text),
        sa.CheckConstraint(
            "event_type IN ('created','relabelled','split','merged','removed','moved_floor',"
            "'geometry_updated','approved')",
            name="ck_lineage_type",
        ),
    )
    op.create_index("ix_unit_lineage_events_tenant_id", "unit_lineage_events", ["tenant_id"])
    op.create_index("ix_unit_lineage_events_project_id", "unit_lineage_events", ["project_id"])

    op.create_table(
        "unit_areas",
        _id(),
        _tenant(),
        _fk("unit_id", "units"),
        sa.Column("area_type", sa.String(40), nullable=False),
        sa.Column("value_m2", sa.Numeric(10, 2), nullable=False),
        sa.Column("source", sa.String(20), nullable=False),
        sa.Column("source_ref", pg.JSONB),
        sa.Column(
            "verification_status", sa.String(20), nullable=False, server_default="unverified"
        ),
        sa.Column("verified_by", pg.UUID(as_uuid=True)),
        sa.Column("verified_at", sa.DateTime(timezone=True)),
        sa.Column("is_current", sa.Boolean, nullable=False, server_default=sa.true()),
        *_ts(),
        sa.CheckConstraint("value_m2 >= 0", name="ck_area_non_negative"),
    )
    op.create_index("ix_unit_areas_tenant_id", "unit_areas", ["tenant_id"])
    op.create_index("ix_unit_areas_unit_id", "unit_areas", ["unit_id"])

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
    for t in [
        "unit_areas",
        "unit_lineage_events",
        "unit_boundaries",
        "unit_code_history",
        "units",
        "sheets",
        "document_revisions",
        "documents",
    ]:
        op.drop_table(t)
