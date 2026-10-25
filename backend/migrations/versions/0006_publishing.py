"""publishing: publications, published read model, portal host resolver, portal settings

Revision ID: 0006
Revises: 0005
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

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None

TENANT_TABLES = ["publications", "published_units"]

# Host → tenant resolution for anonymous portal requests and Caddy's on-demand TLS `ask`.
# portal_domains is tenant-scoped with FORCE ROW LEVEL SECURITY, so an anonymous request
# (no app.tenant_id yet) sees no rows. This SECURITY DEFINER function raises app.scope to
# 'platform' around its single query and restores the caller's value before returning, and
# it returns just the routing columns of one active hostname — never tokens or other rows.
# (A function-level `SET app.scope` clause would be simpler but needs superuser on PG 15+.)
RESOLVER = """
CREATE OR REPLACE FUNCTION portal_resolve_host(h text)
RETURNS TABLE (
  domain_id uuid,
  tenant_id uuid,
  project_id uuid,
  kind text,
  verification_status text,
  tenant_slug text,
  tenant_status text
)
LANGUAGE plpgsql STABLE SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE
  prev text := coalesce(current_setting('app.scope', true), '');
BEGIN
  PERFORM set_config('app.scope', 'platform', true);
  RETURN QUERY
    SELECT d.id, d.tenant_id, d.project_id, d.kind::text, d.verification_status::text,
           t.slug::text, t.status::text
    FROM portal_domains d JOIN tenants t ON t.id = d.tenant_id
    WHERE d.hostname = lower(h) AND d.status = 'active'
    LIMIT 1;
  PERFORM set_config('app.scope', prev, true);
END
$$;
"""


def _id():
    return sa.Column("id", pg.UUID(as_uuid=True), primary_key=True)


def _tenant():
    return sa.Column(
        "tenant_id",
        pg.UUID(as_uuid=True),
        sa.ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
    )


def upgrade() -> None:
    op.add_column(
        "projects",
        sa.Column("portal_settings", pg.JSONB, nullable=False, server_default="{}"),
    )

    op.create_table(
        "publications",
        _id(),
        _tenant(),
        sa.Column(
            "project_id",
            pg.UUID(as_uuid=True),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("version_no", sa.Integer, nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("snapshot_key", sa.String(512), nullable=False),
        sa.Column("summary", pg.JSONB, nullable=False, server_default="{}"),
        sa.Column("assets", pg.JSONB, nullable=False, server_default="{}"),
        sa.Column("created_by", pg.UUID(as_uuid=True)),
        sa.Column("published_at", sa.DateTime(timezone=True)),
        sa.Column("retired_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "status IN ('preview','published','retired')", name="ck_publication_status"
        ),
        sa.UniqueConstraint("project_id", "version_no", name="uq_publication_version"),
    )
    op.create_index("ix_publications_tenant_id", "publications", ["tenant_id"])
    op.create_index("ix_publications_project_id", "publications", ["project_id"])
    # at most one live publication per project: the atomic switch of plan §9.3
    op.execute(
        "CREATE UNIQUE INDEX uq_publications_live ON publications (project_id) "
        "WHERE status = 'published'"
    )

    op.create_table(
        "published_units",
        _id(),
        _tenant(),
        sa.Column(
            "publication_id",
            pg.UUID(as_uuid=True),
            sa.ForeignKey("publications.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("project_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("unit_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("code", sa.String(40), nullable=False),
        sa.Column("building_code", sa.String(20), nullable=False),
        sa.Column("floor_level", sa.Integer, nullable=False),
        sa.Column("unit_type", sa.String(20), nullable=False),
        sa.Column("availability", sa.String(20), nullable=False),
        sa.Column("listed", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("price_amount", sa.Numeric(14, 2)),
        sa.Column("currency", sa.String(3)),
        sa.Column("area_m2", sa.Numeric(10, 2)),
        sa.Column("rooms", sa.Integer),
        sa.Column("bedrooms", sa.Integer),
        sa.Column("sort_order", sa.Integer, nullable=False, server_default="0"),
        sa.Column("data", pg.JSONB, nullable=False),
    )
    op.create_index("ix_published_units_tenant_id", "published_units", ["tenant_id"])
    op.create_index(
        "ix_published_units_pub_listing",
        "published_units",
        ["publication_id", "listed", "availability"],
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_published_units_code ON published_units "
        "(publication_id, lower(code))"
    )

    for t in TENANT_TABLES:
        enable_tenant_rls(t)
    op.execute(RESOLVER)
    op.execute("REVOKE ALL ON FUNCTION portal_resolve_host(text) FROM PUBLIC")
    op.execute(
        """
        DO $$ BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'app_rw') THEN
            GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO app_rw;
            GRANT EXECUTE ON FUNCTION portal_resolve_host(text) TO app_rw;
          END IF;
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'app_portal') THEN
            GRANT EXECUTE ON FUNCTION portal_resolve_host(text) TO app_portal;
            GRANT SELECT ON publications, published_units TO app_portal;
          END IF;
        END $$;
        """
    )


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS portal_resolve_host(text)")
    for t in TENANT_TABLES:
        disable_tenant_rls(t)
    op.drop_table("published_units")
    op.drop_table("publications")
    op.drop_column("projects", "portal_settings")
