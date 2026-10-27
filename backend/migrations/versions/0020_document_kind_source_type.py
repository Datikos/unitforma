"""documents.kind_source gains ``type`` (ADR-0008 amendment of 2026-10-27)

An IFC or GLB upload is a model by its file type, not a guess: the platform sets ``model_ifc`` or
``model_glb`` at the upload intent and again from the sniffed MIME type in the worker, with
``kind_source = type``. Additive (expand): the check constraint gains one value.

Revision ID: 0020
Revises: 0019
Create Date: 2026-10-27
"""

from __future__ import annotations

from alembic import op

revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None

_OLD = "'manual','filename','content','pending','ai'"  # 0010 plus 0019's ``ai``
_NEW = _OLD + ",'type'"


def upgrade() -> None:
    op.drop_constraint("ck_document_kind_source", "documents", type_="check")
    op.create_check_constraint("ck_document_kind_source", "documents", f"kind_source IN ({_NEW})")


def downgrade() -> None:
    # the migration role owns the table and FORCE RLS applies: platform scope sees all rows
    op.execute("SELECT set_config('app.scope', 'platform', true)")
    op.execute("UPDATE documents SET kind_source = 'content' WHERE kind_source = 'type'")
    op.execute("SELECT set_config('app.scope', '', true)")
    op.drop_constraint("ck_document_kind_source", "documents", type_="check")
    op.create_check_constraint("ck_document_kind_source", "documents", f"kind_source IN ({_OLD})")
