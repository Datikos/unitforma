import uuid

import pytest

from unitforma.identity.authz import (
    RESOURCES,
    Action,
    MembershipContext,
    Role,
    can_access_project,
    is_allowed,
)


def ctx(role: Role, **kw) -> MembershipContext:
    return MembershipContext(tenant_id=uuid.uuid4(), user_id=uuid.uuid4(), role=role, **kw)


def test_tenant_admin_can_do_everything():
    c = ctx(Role.TENANT_ADMIN)
    for resource in RESOURCES:
        assert is_allowed(c, resource, Action.READ)


@pytest.mark.parametrize("role", [Role.SALES, Role.PROJECT_MANAGER, Role.ARCHITECTURAL_REVIEWER])
def test_only_tenant_admin_manages_users_and_domains(role):
    c = ctx(role)
    assert not is_allowed(c, "tenant.users", Action.READ)
    assert not is_allowed(c, "tenant.domains", Action.WRITE)


def test_reviewer_approves_mapping_but_sales_does_not():
    assert is_allowed(ctx(Role.ARCHITECTURAL_REVIEWER), "mapping", Action.APPROVE)
    assert not is_allowed(ctx(Role.SALES), "mapping", Action.APPROVE)
    assert not is_allowed(ctx(Role.PROJECT_MANAGER), "mapping", Action.APPROVE)


def test_sales_writes_sales_and_leads_only():
    c = ctx(Role.SALES)
    assert is_allowed(c, "sales", Action.WRITE)
    assert is_allowed(c, "leads", Action.WRITE)
    assert not is_allowed(c, "documents", Action.WRITE)
    assert not is_allowed(c, "publication", Action.PUBLISH)


def test_suspended_membership_has_no_rights():
    c = ctx(Role.TENANT_ADMIN, is_active=False)
    assert not is_allowed(c, "project", Action.READ)
    assert not can_access_project(c, uuid.uuid4())


def test_project_restriction():
    p1, p2 = uuid.uuid4(), uuid.uuid4()
    c = ctx(Role.SALES, all_projects=False, project_ids=frozenset({p1}))
    assert can_access_project(c, p1)
    assert not can_access_project(c, p2)


def test_unknown_resource_is_a_programming_error():
    with pytest.raises(KeyError):
        is_allowed(ctx(Role.TENANT_ADMIN), "nonexistent", Action.READ)
