"""ADR-0030 #D2: a floor sheet registered to its building on the drawing's grid axes

``sheet_floors.registration`` holds the shift that moves the floor's outlines from the sheet's
own origin onto the building's reference floor, with the axes it was found from. Written by the
solver's ``registration`` pass, read when outlines are put in building metres; ``null`` means
not registered yet (the outlines stay as drawn, as before).
Additive (expand): nullable, compatible with the previous release.

Revision ID: 0023
Revises: 0022
Create Date: 2026-10-30
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0023"
down_revision = "0022"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("sheet_floors", sa.Column("registration", postgresql.JSONB(), nullable=True))


def downgrade() -> None:
    op.drop_column("sheet_floors", "registration")
