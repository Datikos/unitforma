"""documents.kind_source and the unclassified kind (ADR-0008)

Documents classify themselves from the file name at creation and from page content after
processing; ``kind_source`` says who set the current kind (manual | filename | content |
pending) so the reviewer sees what still needs confirming. Existing rows were set by hand.
Additive (expand): the check constraint on ``kind`` gains one value.

Revision ID: 0010
Revises: 0009
Create Date: 2026-10-25
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None

_KINDS_OLD = (
    "'site_plan','floor_plan','section','elevation','render','schedule',"
    "'model_ifc','model_glb','texture','permit','other'"
)
_KINDS_NEW = _KINDS_OLD + ",'unclassified'"


def upgrade() -> None:
    op.add_column(
        "documents",
        sa.Column("kind_source", sa.String(20), nullable=False, server_default="manual"),
    )
    op.create_check_constraint(
        "ck_document_kind_source",
        "documents",
        "kind_source IN ('manual','filename','content','pending')",
    )
    op.drop_constraint("ck_document_kind", "documents", type_="check")
    op.create_check_constraint("ck_document_kind", "documents", f"kind IN ({_KINDS_NEW})")


def downgrade() -> None:
    # the migration role owns the table and FORCE RLS applies: platform scope sees all rows
    op.execute("SELECT set_config('app.scope', 'platform', true)")
    op.execute("UPDATE documents SET kind = 'other' WHERE kind = 'unclassified'")
    op.execute("SELECT set_config('app.scope', '', true)")
    op.drop_constraint("ck_document_kind", "documents", type_="check")
    op.create_check_constraint("ck_document_kind", "documents", f"kind IN ({_KINDS_OLD})")
    op.drop_constraint("ck_document_kind_source", "documents", type_="check")
    op.drop_column("documents", "kind_source")
