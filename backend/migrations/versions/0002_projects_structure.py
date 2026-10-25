"""projects, buildings, floors, site features, membership project access

Revision ID: 0002
Revises: 0001
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

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

TENANT_TABLES = ["projects", "buildings", "floors", "site_features", "membership_project_access"]


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
    tenant_fk = lambda: sa.Column(  # noqa: E731
        "tenant_id",
        pg.UUID(as_uuid=True),
        sa.ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
    )
    op.create_table(
        "projects",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        tenant_fk(),
        sa.Column("slug", sa.String(63), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="draft"),
        sa.Column("currency", sa.String(3), nullable=False, server_default="EUR"),
        sa.Column("address", pg.JSONB, nullable=False, server_default="{}"),
        sa.Column(
            "code_pattern",
            sa.String(80),
            nullable=False,
            server_default="{building}-{floor:02}-{seq:02}",
        ),
        sa.Column("area_definitions", pg.JSONB, nullable=False, server_default="[]"),
        sa.Column("site_frame", pg.JSONB, nullable=False, server_default="{}"),
        sa.Column("description", sa.Text),
        sa.Column("regulatory", pg.JSONB, nullable=False, server_default="{}"),
        sa.Column("version", sa.Integer, nullable=False, server_default="1"),
        *_ts(),
        sa.UniqueConstraint("tenant_id", "slug", name="uq_project_slug"),
        sa.CheckConstraint("status IN ('draft','active','archived')", name="ck_project_status"),
    )
    op.create_index("ix_projects_tenant_id", "projects", ["tenant_id"])
    op.create_table(
        "buildings",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        tenant_fk(),
        sa.Column(
            "project_id",
            pg.UUID(as_uuid=True),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("code", sa.String(20), nullable=False),
        sa.Column("name", sa.String(200)),
        sa.Column("kind", sa.String(20), nullable=False, server_default="building"),
        sa.Column("site_transform", pg.JSONB, nullable=False, server_default="{}"),
        sa.Column("placement_status", sa.String(20), nullable=False, server_default="unplaced"),
        sa.Column("sort_order", sa.Integer, nullable=False, server_default="0"),
        sa.Column("version", sa.Integer, nullable=False, server_default="1"),
        *_ts(),
        sa.UniqueConstraint("project_id", "code", name="uq_building_code"),
        sa.CheckConstraint("kind IN ('building','site')", name="ck_building_kind"),
    )
    op.create_index("ix_buildings_tenant_id", "buildings", ["tenant_id"])
    op.create_index("ix_buildings_project_id", "buildings", ["project_id"])
    op.create_table(
        "floors",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        tenant_fk(),
        sa.Column(
            "building_id",
            pg.UUID(as_uuid=True),
            sa.ForeignKey("buildings.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("level", sa.Integer, nullable=False),
        sa.Column("display_name", sa.String(80), nullable=False),
        sa.Column("height_m", sa.Numeric(6, 3)),
        sa.Column("elevation_m", sa.Numeric(8, 3)),
        sa.Column("sort_order", sa.Integer, nullable=False, server_default="0"),
        sa.Column("version", sa.Integer, nullable=False, server_default="1"),
        *_ts(),
        sa.UniqueConstraint("building_id", "level", name="uq_floor_level"),
    )
    op.create_index("ix_floors_tenant_id", "floors", ["tenant_id"])
    op.create_index("ix_floors_building_id", "floors", ["building_id"])
    op.create_table(
        "site_features",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        tenant_fk(),
        sa.Column(
            "project_id",
            pg.UUID(as_uuid=True),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("kind", sa.String(30), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("polygon", pg.JSONB),
        sa.Column("is_public", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("sort_order", sa.Integer, nullable=False, server_default="0"),
        *_ts(),
    )
    op.create_index("ix_site_features_tenant_id", "site_features", ["tenant_id"])
    op.create_index("ix_site_features_project_id", "site_features", ["project_id"])
    op.create_table(
        "membership_project_access",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        tenant_fk(),
        sa.Column(
            "membership_id",
            pg.UUID(as_uuid=True),
            sa.ForeignKey("memberships.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "project_id",
            pg.UUID(as_uuid=True),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.UniqueConstraint("membership_id", "project_id", name="uq_mpa"),
    )
    op.create_index("ix_mpa_tenant_id", "membership_project_access", ["tenant_id"])
    op.create_index("ix_mpa_membership_id", "membership_project_access", ["membership_id"])
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
    for t in ["membership_project_access", "site_features", "floors", "buildings", "projects"]:
        op.drop_table(t)
