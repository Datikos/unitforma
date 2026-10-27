"""The tool registry entry (ADR-0028 Decision 6): a plain async function, its access tag and the
hints an MCP client reads. The registry list is the one home of the tools; the MCP server is one
consumer of it."""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, Literal

from mcp.types import ToolAnnotations

from unitforma.identity.deps import TenantContext


@dataclass(frozen=True)
class Tool:
    """``tag`` is ``read`` or ``write``. A write tool opens ``tenant_ctx(write=True)`` as its
    first statement, so a read token is refused before anything runs (tested for every entry).

    ``destructive``: the call changes or replaces what exists (an update, a floor list, the
    solver's switches); ``False`` when it only adds. ``idempotent``: the same call twice leaves
    the same state. ``open_world``: the call reaches a party outside Unitforma (the image model).
    """

    fn: Callable[..., Awaitable[Any]]
    tag: Literal["read", "write"]
    title: str
    destructive: bool = False
    idempotent: bool = False
    open_world: bool = False

    @property
    def name(self) -> str:
        return self.fn.__name__

    def annotations(self) -> ToolAnnotations:
        read = self.tag == "read"
        return ToolAnnotations(
            title=self.title,
            read_only_hint=read,
            destructive_hint=False if read else self.destructive,
            idempotent_hint=True if read else self.idempotent,
            open_world_hint=self.open_world,
        )


def actor(ctx: TenantContext) -> tuple[uuid.UUID, str]:
    return ctx.principal.user_id, ctx.actor_role
