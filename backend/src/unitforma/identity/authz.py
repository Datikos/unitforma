"""Authorization policy matrix (plan §3.4).

Roles are per tenant membership; platform administrators are a flag on the user.
Every admin API handler asks :func:`is_allowed` with the caller's membership, the
resource type and the action. Project restrictions are checked separately with
:func:`can_access_project`.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from enum import StrEnum


class Role(StrEnum):
    TENANT_ADMIN = "tenant_admin"
    PROJECT_MANAGER = "project_manager"
    SALES = "sales"
    ARCHITECTURAL_REVIEWER = "architectural_reviewer"


class Action(StrEnum):
    READ = "read"
    WRITE = "write"
    APPROVE = "approve"
    PUBLISH = "publish"
    MANAGE = "manage"


# resource -> role -> allowed actions
_MATRIX: dict[str, dict[Role, frozenset[Action]]] = {
    "tenant.settings": {Role.TENANT_ADMIN: frozenset({Action.READ, Action.WRITE, Action.MANAGE})},
    "tenant.users": {Role.TENANT_ADMIN: frozenset({Action.READ, Action.WRITE, Action.MANAGE})},
    "tenant.domains": {Role.TENANT_ADMIN: frozenset({Action.READ, Action.WRITE, Action.MANAGE})},
    "project": {
        Role.TENANT_ADMIN: frozenset(Action),
        Role.PROJECT_MANAGER: frozenset({Action.READ, Action.WRITE, Action.PUBLISH}),
        Role.SALES: frozenset({Action.READ}),
        Role.ARCHITECTURAL_REVIEWER: frozenset({Action.READ}),
    },
    "documents": {
        Role.TENANT_ADMIN: frozenset(Action),
        Role.PROJECT_MANAGER: frozenset({Action.READ, Action.WRITE}),
        Role.SALES: frozenset({Action.READ}),
        Role.ARCHITECTURAL_REVIEWER: frozenset({Action.READ, Action.WRITE}),
    },
    "mapping": {
        Role.TENANT_ADMIN: frozenset(Action),
        Role.PROJECT_MANAGER: frozenset({Action.READ}),
        Role.SALES: frozenset({Action.READ}),
        Role.ARCHITECTURAL_REVIEWER: frozenset({Action.READ, Action.WRITE, Action.APPROVE}),
    },
    "sales": {
        Role.TENANT_ADMIN: frozenset(Action),
        Role.PROJECT_MANAGER: frozenset({Action.READ, Action.WRITE}),
        Role.SALES: frozenset({Action.READ, Action.WRITE}),
        Role.ARCHITECTURAL_REVIEWER: frozenset({Action.READ}),
    },
    "leads": {
        Role.TENANT_ADMIN: frozenset(Action),
        Role.PROJECT_MANAGER: frozenset({Action.READ, Action.WRITE}),
        Role.SALES: frozenset({Action.READ, Action.WRITE}),
        Role.ARCHITECTURAL_REVIEWER: frozenset({Action.READ}),
    },
    "publication": {
        Role.TENANT_ADMIN: frozenset(Action),
        Role.PROJECT_MANAGER: frozenset({Action.READ, Action.PUBLISH}),
        Role.SALES: frozenset({Action.READ}),
        Role.ARCHITECTURAL_REVIEWER: frozenset({Action.READ}),
    },
}

RESOURCES = frozenset(_MATRIX)


@dataclass(frozen=True)
class MembershipContext:
    tenant_id: uuid.UUID
    user_id: uuid.UUID
    role: Role
    all_projects: bool = True
    project_ids: frozenset[uuid.UUID] = field(default_factory=frozenset)
    is_active: bool = True
    is_member: bool = True  # False for the context a platform admin gets without a membership row


def is_allowed(ctx: MembershipContext, resource: str, action: Action) -> bool:
    if not ctx.is_active:
        return False
    if resource not in _MATRIX:
        raise KeyError(f"unknown resource {resource!r}")
    return action in _MATRIX[resource].get(ctx.role, frozenset())


def can_access_project(ctx: MembershipContext, project_id: uuid.UUID) -> bool:
    if not ctx.is_active:
        return False
    return ctx.all_projects or project_id in ctx.project_ids
