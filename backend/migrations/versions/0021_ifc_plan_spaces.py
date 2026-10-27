"""ADR-0030: a note on a repeated upload, the source of an IFC space link

``document_revisions.processing_note`` carries a neutral remark the card shows without the red
error alert ("Same file as <document> rev <n>"). ``ifc_space_links.source`` says whether a space
came from an ``IfcSpace`` of the file (``ifc``) or from an approved plan outline placed in the IFC
frame (``plan``). Both additive (expand): nullable or defaulted, compatible with the previous
release.

Revision ID: 0021
Revises: 0020
Create Date: 2026-10-27
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0021"
down_revision = "0020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("document_revisions", sa.Column("processing_note", sa.String(300), nullable=True))
    op.add_column(
        "ifc_space_links",
        sa.Column("source", sa.String(10), nullable=False, server_default="ifc"),
    )
    op.create_check_constraint(
        "ck_ifc_space_link_source", "ifc_space_links", "source IN ('ifc','plan')"
    )


def downgrade() -> None:
    op.drop_constraint("ck_ifc_space_link_source", "ifc_space_links", type_="check")
    op.drop_column("ifc_space_links", "source")
    op.drop_column("document_revisions", "processing_note")
