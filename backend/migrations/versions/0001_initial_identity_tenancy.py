"""initial identity, tenancy, domains, audit

Revision ID: 0001
Revises:
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

from unitforma.core.slugs import RESERVED_SUBDOMAINS  # noqa: E402

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

TENANT_TABLES = ["memberships", "staff_invitations", "portal_domains"]


def upgrade() -> None:
    op.create_table(
        "tenants",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("slug", sa.String(63), nullable=False, unique=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column("default_currency", sa.String(3), nullable=False, server_default="EUR"),
        sa.Column("branding", pg.JSONB, nullable=False, server_default="{}"),
        sa.Column("settings", pg.JSONB, nullable=False, server_default="{}"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_table(
        "users",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("kratos_identity_id", pg.UUID(as_uuid=True), nullable=False, unique=True),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("display_name", sa.String(200)),
        sa.Column("is_platform_admin", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("last_seen_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_users_email", "users", ["email"])
    op.create_table(
        "memberships",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            pg.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            pg.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("role", sa.String(40), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="invited"),
        sa.Column("all_projects", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("invited_by", pg.UUID(as_uuid=True)),
        sa.Column("accepted_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("tenant_id", "user_id", name="uq_membership_tenant_user"),
        sa.CheckConstraint(
            "role IN ('tenant_admin','project_manager','sales','architectural_reviewer')",
            name="ck_membership_role",
        ),
    )
    op.create_index("ix_memberships_tenant_id", "memberships", ["tenant_id"])
    op.create_index("ix_memberships_user_id", "memberships", ["user_id"])
    op.create_table(
        "staff_invitations",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            pg.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("role", sa.String(40), nullable=False),
        sa.Column(
            "project_ids", pg.ARRAY(pg.UUID(as_uuid=True)), nullable=False, server_default="{}"
        ),
        sa.Column("token_hash", sa.String(128), nullable=False, unique=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("accepted_membership_id", pg.UUID(as_uuid=True)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_staff_invitations_tenant_id", "staff_invitations", ["tenant_id"])
    op.create_table("reserved_subdomains", sa.Column("name", sa.String(63), primary_key=True))
    op.bulk_insert(
        sa.table("reserved_subdomains", sa.column("name", sa.String)),
        [{"name": n} for n in sorted(RESERVED_SUBDOMAINS)],
    )
    op.create_table(
        "portal_domains",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            pg.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("project_id", pg.UUID(as_uuid=True)),
        sa.Column("hostname", sa.String(253), nullable=False, unique=True),
        sa.Column("kind", sa.String(30), nullable=False),
        sa.Column("verification_token", sa.String(80)),
        sa.Column("verification_status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("verified_at", sa.DateTime(timezone=True)),
        sa.Column("last_checked_at", sa.DateTime(timezone=True)),
        sa.Column("tls_status", sa.String(20)),
        sa.Column("is_primary", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column("removed_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("kind IN ('platform_subdomain','custom')", name="ck_portal_domain_kind"),
        sa.CheckConstraint(
            "status IN ('active','disabled','removed')", name="ck_portal_domain_status"
        ),
    )
    op.create_index("ix_portal_domains_tenant_id", "portal_domains", ["tenant_id"])
    op.create_table(
        "audit_log",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", pg.UUID(as_uuid=True)),
        sa.Column("actor_user_id", pg.UUID(as_uuid=True)),
        sa.Column("actor_role", sa.String(40)),
        sa.Column("entity_type", sa.String(60), nullable=False),
        sa.Column("entity_id", pg.UUID(as_uuid=True)),
        sa.Column("action", sa.String(40), nullable=False),
        sa.Column("before", pg.JSONB),
        sa.Column("after", pg.JSONB),
        sa.Column("request_id", sa.Text),
        sa.Column("at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_audit_log_tenant_id", "audit_log", ["tenant_id"])

    for t in TENANT_TABLES:
        enable_tenant_rls(t)

    # tenants: a tenant row is visible to its own members (app.tenant_id) and to platform scope.
    op.execute("ALTER TABLE tenants ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE tenants FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY tenant_self ON tenants "
        "USING (id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)"
    )
    op.execute(
        "CREATE POLICY platform_scope ON tenants "
        "USING (current_setting('app.scope', true) = 'platform') "
        "WITH CHECK (current_setting('app.scope', true) = 'platform')"
    )
    # audit_log: append-only for everyone, readable per tenant / platform.
    op.execute("ALTER TABLE audit_log ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE audit_log FORCE ROW LEVEL SECURITY")
    op.execute("CREATE POLICY audit_insert ON audit_log FOR INSERT WITH CHECK (true)")
    op.execute(
        "CREATE POLICY audit_read_tenant ON audit_log FOR SELECT "
        "USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid "
        "OR current_setting('app.scope', true) = 'platform')"
    )

    # Grants for the runtime roles created by deploy/postgres/initdb/00-roles.sql.
    op.execute(
        """
        DO $$ BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'app_rw') THEN
            GRANT USAGE ON SCHEMA public TO app_rw;
            GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO app_rw;
            GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO app_rw;
          END IF;
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'app_portal') THEN
            GRANT USAGE ON SCHEMA public TO app_portal;
            GRANT SELECT ON tenants, portal_domains TO app_portal;
          END IF;
        END $$;
        """
    )


def downgrade() -> None:
    for t in TENANT_TABLES:
        disable_tenant_rls(t)
    for t in [
        "audit_log",
        "portal_domains",
        "reserved_subdomains",
        "staff_invitations",
        "memberships",
        "users",
        "tenants",
    ]:
        op.drop_table(t)
