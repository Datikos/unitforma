"""Setup tools (ADR-0025, ADR-0028 Decision 6): the checklist with the solver's decisions, "Run
now" and the solver's switches, through the same functions as the admin API
(``autopilot/control.py``). Publishing with defaults (ADR-0029) stays a person's click."""

from __future__ import annotations

import uuid

from unitforma.api.schemas import SetupAutoOut, SetupOut, SetupRunOut
from unitforma.autopilot import control
from unitforma.mcp.auth import tenant_ctx
from unitforma.mcp.tools.base import Tool


async def get_setup_checklist(project_id: uuid.UUID) -> SetupOut:
    """The project's setup checklist in the order of work: each step's state and what it still
    needs, what the setup solver applied with its confidence, and what it left for a person."""
    async with tenant_ctx() as ctx:
        return SetupOut.model_validate(await control.checklist(ctx, project_id))


async def run_setup(project_id: uuid.UUID) -> SetupRunOut:
    """Queue one run of the setup solver now, whether or not it is switched on. It applies the
    confident proposals (floors, sheets to floors, scale, clear unit outlines, placement, …) as
    you, and leaves the rest on the checklist. The run starts as "queued"; read the checklist
    again after it finishes."""
    async with tenant_ctx(write=True) as ctx:
        return SetupRunOut.model_validate(await control.run_now(ctx, project_id))


async def set_setup_auto(
    project_id: uuid.UUID, enabled: bool, approve_sheets: bool = True
) -> SetupAutoOut:
    """Switch the setup solver on or off for the project. When on, it runs after every processed
    document as you; `approve_sheets` lets it approve the unit outlines it is sure of (needs the
    mapping approve right). Switching on queues a run at once. Publishing with defaults is not
    changed here."""
    async with tenant_ctx(write=True) as ctx:
        return SetupAutoOut.model_validate(
            await control.switch(
                ctx,
                project_id,
                enabled=enabled,
                approve_sheets=approve_sheets,
                publish_defaults=None,
            )
        )


TOOLS = [
    Tool(get_setup_checklist, "read", "Setup checklist"),
    Tool(run_setup, "write", "Run the setup solver now", destructive=True),
    Tool(set_setup_auto, "write", "Switch the setup solver", destructive=True, idempotent=True),
]
