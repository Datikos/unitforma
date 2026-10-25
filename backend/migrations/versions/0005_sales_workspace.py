"""sales workspace: unit_sales, history, payment plans, promotions, media, import batches

Revision ID: 0005
Revises: 0004
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

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None

TENANT_TABLES = [
    "payment_plans",
    "promotions",
    "unit_sales",
    "price_history",
    "availability_history",
    "unit_media",
    "import_batches",
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


AVAILABILITY = "('available','reserved','sold','withdrawn')"


def upgrade() -> None:
    # expand-only change to an existing table (plan §5.6): nullable-safe default
    op.add_column(
        "projects",
        sa.Column("sales_settings", pg.JSONB, nullable=False, server_default="{}"),
    )

    op.create_table(
        "payment_plans",
        _id(),
        _tenant(),
        _fk("project_id", "projects"),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("description", sa.Text),
        sa.Column("schedule", pg.JSONB, nullable=False, server_default="[]"),
        sa.Column("is_public", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("sort_order", sa.Integer, nullable=False, server_default="0"),
        _version(),
        *_ts(),
    )
    op.create_index("ix_payment_plans_tenant_id", "payment_plans", ["tenant_id"])
    op.create_index("ix_payment_plans_project_id", "payment_plans", ["project_id"])
    op.execute(
        "CREATE UNIQUE INDEX uq_payment_plans_name ON payment_plans (project_id, lower(name))"
    )

    op.create_table(
        "promotions",
        _id(),
        _tenant(),
        _fk("project_id", "projects"),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("kind", sa.String(30), nullable=False, server_default="other"),
        sa.Column("value", sa.Numeric(14, 2)),
        sa.Column("terms", sa.Text),
        sa.Column("valid_from", sa.Date),
        sa.Column("valid_to", sa.Date),
        sa.Column("is_public", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.true()),
        _version(),
        *_ts(),
        sa.CheckConstraint(
            "kind IN ('discount_percent','discount_amount','gift','financing','other')",
            name="ck_promotion_kind",
        ),
        sa.CheckConstraint("value IS NULL OR value >= 0", name="ck_promotion_value"),
        sa.CheckConstraint(
            "valid_to IS NULL OR valid_from IS NULL OR valid_to >= valid_from",
            name="ck_promotion_dates",
        ),
    )
    op.create_index("ix_promotions_tenant_id", "promotions", ["tenant_id"])
    op.create_index("ix_promotions_project_id", "promotions", ["project_id"])
    op.execute("CREATE UNIQUE INDEX uq_promotions_name ON promotions (project_id, lower(name))")

    op.create_table(
        "unit_sales",
        sa.Column(
            "unit_id",
            pg.UUID(as_uuid=True),
            sa.ForeignKey("units.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        _tenant(),
        _fk("project_id", "projects"),
        sa.Column("availability", sa.String(20), nullable=False, server_default="available"),
        sa.Column("availability_reason", sa.Text),
        sa.Column("availability_changed_at", sa.DateTime(timezone=True)),
        sa.Column("list_price", sa.Numeric(14, 2)),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("price_on_request", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("price_area_type", sa.String(40)),
        _fk("payment_plan_id", "payment_plans", "SET NULL", True),
        sa.Column(
            "promotion_ids", pg.ARRAY(pg.UUID(as_uuid=True)), nullable=False, server_default="{}"
        ),
        sa.Column("public_description", sa.Text),
        sa.Column("internal_notes", sa.Text),
        sa.Column("public_fields", pg.JSONB, nullable=False, server_default="{}"),
        sa.Column("updated_by", pg.UUID(as_uuid=True)),
        _version(),
        *_ts(),
        sa.CheckConstraint(f"availability IN {AVAILABILITY}", name="ck_unit_sales_availability"),
        # prices are numeric and NULL means unknown — never a silent 0 (AGENTS.md rule 3)
        sa.CheckConstraint("list_price IS NULL OR list_price >= 0", name="ck_unit_sales_price"),
        sa.CheckConstraint("currency ~ '^[A-Z]{3}$'", name="ck_unit_sales_currency"),
    )
    op.create_index("ix_unit_sales_tenant_id", "unit_sales", ["tenant_id"])
    op.create_index("ix_unit_sales_project_id", "unit_sales", ["project_id"])

    for name, cols in (
        (
            "price_history",
            [
                sa.Column("old_price", sa.Numeric(14, 2)),
                sa.Column("new_price", sa.Numeric(14, 2)),
                sa.Column("old_currency", sa.String(3)),
                sa.Column("new_currency", sa.String(3)),
            ],
        ),
        (
            "availability_history",
            [
                sa.Column("old_availability", sa.String(20)),
                sa.Column("new_availability", sa.String(20), nullable=False),
            ],
        ),
    ):
        op.create_table(
            name,
            _id(),
            _tenant(),
            _fk("unit_id", "units"),
            *cols,
            sa.Column("changed_by", pg.UUID(as_uuid=True)),
            sa.Column(
                "changed_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.Column("reason", sa.Text),
            sa.Column("import_batch_id", pg.UUID(as_uuid=True)),
        )
        op.create_index(f"ix_{name}_tenant_id", name, ["tenant_id"])
        op.create_index(f"ix_{name}_unit_id", name, ["unit_id"])

    op.create_table(
        "unit_media",
        _id(),
        _tenant(),
        _fk("project_id", "projects"),
        _fk("unit_id", "units"),
        sa.Column("kind", sa.String(30), nullable=False, server_default="photo"),
        sa.Column("object_key", sa.String(512), nullable=False),
        sa.Column("file_name", sa.String(255), nullable=False),
        sa.Column("mime", sa.String(120), nullable=False),
        sa.Column("byte_size", sa.BigInteger),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("sort_order", sa.Integer, nullable=False, server_default="0"),
        sa.Column("is_public", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("alt_text", sa.String(300)),
        sa.Column("is_ai_generated", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("ai_disclosure_text", sa.String(300)),
        sa.Column("uploaded_by", pg.UUID(as_uuid=True)),
        _version(),
        *_ts(),
        sa.CheckConstraint(
            "kind IN ('plan_render','interior_render','exterior_render','photo','video',"
            "'document')",
            name="ck_unit_media_kind",
        ),
        sa.CheckConstraint("status IN ('pending','ready')", name="ck_unit_media_status"),
        # AI-generated media carries its disclosure at the data level (plan §5.3 unit_media)
        sa.CheckConstraint(
            "NOT is_ai_generated OR ai_disclosure_text IS NOT NULL",
            name="ck_unit_media_ai_disclosure",
        ),
    )
    op.create_index("ix_unit_media_tenant_id", "unit_media", ["tenant_id"])
    op.create_index("ix_unit_media_unit_id", "unit_media", ["unit_id"])
    op.create_index("ix_unit_media_project_id", "unit_media", ["project_id"])

    op.create_table(
        "import_batches",
        _id(),
        _tenant(),
        _fk("project_id", "projects"),
        sa.Column("file_name", sa.String(255), nullable=False),
        sa.Column("object_key", sa.String(512), nullable=False),
        sa.Column("file_format", sa.String(10), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="uploaded"),
        sa.Column("headers", pg.JSONB, nullable=False, server_default="[]"),
        sa.Column("mapping", pg.JSONB, nullable=False, server_default="{}"),
        sa.Column("options", pg.JSONB, nullable=False, server_default="{}"),
        sa.Column("report", pg.JSONB, nullable=False, server_default="{}"),
        sa.Column("row_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("change_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("error_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("created_by", pg.UUID(as_uuid=True)),
        sa.Column("applied_by", pg.UUID(as_uuid=True)),
        sa.Column("applied_at", sa.DateTime(timezone=True)),
        *_ts(),
        sa.CheckConstraint("file_format IN ('csv','xlsx')", name="ck_import_format"),
        sa.CheckConstraint(
            "status IN ('uploaded','dry_run','applied','discarded')", name="ck_import_status"
        ),
    )
    op.create_index("ix_import_batches_tenant_id", "import_batches", ["tenant_id"])
    op.create_index("ix_import_batches_project_id", "import_batches", ["project_id"])

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
        "import_batches",
        "unit_media",
        "availability_history",
        "price_history",
        "unit_sales",
        "promotions",
        "payment_plans",
    ]:
        op.drop_table(t)
    op.drop_column("projects", "sales_settings")
