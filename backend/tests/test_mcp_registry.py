"""The tool registry (ADR-0028 #C1) without a database: names are unique, every tool states what
it does, and every tool tagged ``write`` refuses a read token before its body touches anything.
The last one is the rule that keeps a new write tool from slipping past a read token."""

from __future__ import annotations

import asyncio
import inspect
import uuid

import pytest
from mcp.server.mcpserver.exceptions import ToolError

from unitforma.identity.tokens import TokenPrincipal
from unitforma.mcp import auth
from unitforma.mcp.server import build_server
from unitforma.mcp.tools import TOOLS


def test_names_are_unique_and_every_tool_is_documented():
    names = [t.name for t in TOOLS]
    assert len(names) == len(set(names)) == 25
    for t in TOOLS:
        assert t.tag in ("read", "write")
        assert t.title and (t.fn.__doc__ or "").strip(), t.name


@pytest.mark.parametrize("tool", [t for t in TOOLS if t.tag == "write"], ids=lambda t: t.name)
def test_every_write_tool_refuses_a_read_token_first(tool):
    principal = TokenPrincipal(
        token_id=uuid.uuid4(),
        token_prefix="ufm_test0000",  # noqa: S106 - a prefix, not a secret
        tenant_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        scope="read",
    )
    args = {p: None for p in inspect.signature(tool.fn).parameters}
    token = auth._principal.set(principal)
    try:
        with pytest.raises(ToolError, match="read-only"):
            asyncio.run(tool.fn(**args))
    finally:
        auth._principal.reset(token)


def test_the_server_publishes_the_registry_with_its_hints():
    listed = {t.name: t for t in asyncio.run(build_server().list_tools())}
    assert set(listed) == {t.name for t in TOOLS}
    for t in TOOLS:
        a = listed[t.name].annotations
        assert a.read_only_hint is (t.tag == "read"), t.name
        assert listed[t.name].title == t.title
    assert listed["request_render"].annotations.open_world_hint is True
