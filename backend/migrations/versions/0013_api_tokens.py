"""api_tokens: personal API tokens for non-browser clients, one per user per tenant
(ADR-0015 Decision 2)

Additive: a new table with the standard tenant RLS policies; the running release never reads it.
The secret itself is never stored, only its SHA-256 and a 12-character prefix for lists.

Revision ID: 0013
Revises: 0012
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

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "api_tokens",
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
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("token_prefix", sa.String(16), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("scope", sa.String(10), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("scope IN ('read', 'write')", name="ck_api_token_scope"),
    )
    op.create_index("ix_api_tokens_tenant_user", "api_tokens", ["tenant_id", "user_id"])
    enable_tenant_rls("api_tokens")


def downgrade() -> None:
    disable_tenant_rls("api_tokens")
    op.drop_index("ix_api_tokens_tenant_user", table_name="api_tokens")
    op.drop_table("api_tokens")
