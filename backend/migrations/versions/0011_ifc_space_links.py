"""ifc_space_links: IFC spaces of an ingested model and their reviewed link to units (ADR-0006 C1)

An IFC export (ArchiCAD, Revit) is converted to a GLB per building and its ``IfcSpace`` objects
are listed here with storey, footprint and quantities. The reviewer confirms which unit each space
is: unit ids never change through an IFC import, only the link. Additive.

Revision ID: 0011
Revises: 0010
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

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ifc_space_links",
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
            "building_id",
            pg.UUID(as_uuid=True),
            sa.ForeignKey("buildings.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "geometry_model_id",
            pg.UUID(as_uuid=True),
            sa.ForeignKey("geometry_models.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("ifc_global_id", sa.String(22), nullable=False),
        sa.Column("name", sa.String(200)),
        sa.Column("long_name", sa.String(200)),
        sa.Column("storey_name", sa.String(200)),
        sa.Column("storey_elevation_m", sa.Numeric(8, 3)),
        sa.Column(
            "floor_id", pg.UUID(as_uuid=True), sa.ForeignKey("floors.id", ondelete="SET NULL")
        ),
        sa.Column("unit_id", pg.UUID(as_uuid=True), sa.ForeignKey("units.id", ondelete="SET NULL")),
        sa.Column("status", sa.String(20), nullable=False, server_default="unmatched"),
        sa.Column("confidence", sa.Numeric(3, 2)),
        sa.Column("footprint_m", pg.JSONB),
        sa.Column("areas", pg.JSONB, nullable=False, server_default="{}"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("geometry_model_id", "ifc_global_id", name="uq_ifc_space_per_model"),
        sa.CheckConstraint(
            "status IN ('unmatched','suggested','confirmed','rejected')",
            name="ck_ifc_space_link_status",
        ),
    )
    op.create_index("ix_ifc_space_links_tenant_id", "ifc_space_links", ["tenant_id"])
    op.create_index("ix_ifc_space_links_building_id", "ifc_space_links", ["building_id"])
    op.create_index("ix_ifc_space_links_model_id", "ifc_space_links", ["geometry_model_id"])
    enable_tenant_rls("ifc_space_links")
    op.execute(
        """
        DO $$ BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'app_rw') THEN
            GRANT SELECT, INSERT, UPDATE, DELETE ON ifc_space_links TO app_rw;
          END IF;
        END $$;
        """
    )


def downgrade() -> None:
    disable_tenant_rls("ifc_space_links")
    op.drop_table("ifc_space_links")
