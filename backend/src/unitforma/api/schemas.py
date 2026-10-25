"""Pydantic request/response models for the admin and platform APIs."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field

RoleName = Literal["tenant_admin", "project_manager", "sales", "architectural_reviewer"]


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# --- identity -------------------------------------------------------------------------
class MembershipSummary(ORM):
    tenant_id: uuid.UUID
    tenant_slug: str
    tenant_name: str
    role: RoleName
    status: str
    all_projects: bool


class MeOut(BaseModel):
    user_id: uuid.UUID
    email: str
    email_verified: bool
    is_platform_admin: bool
    aal: str
    memberships: list[MembershipSummary]


# --- tenants --------------------------------------------------------------------------
class TenantCreate(BaseModel):
    slug: str = Field(min_length=3, max_length=63)
    name: str = Field(min_length=1, max_length=200)
    default_currency: str = Field(default="EUR", min_length=3, max_length=3)
    admin_email: EmailStr | None = Field(
        default=None, description="If set, an invitation for the first tenant admin is created"
    )


class TenantUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    default_currency: str | None = Field(default=None, min_length=3, max_length=3)
    branding: dict[str, Any] | None = None
    settings: dict[str, Any] | None = None
    status: Literal["active", "suspended"] | None = None


class TenantOut(ORM):
    id: uuid.UUID
    slug: str
    name: str
    status: str
    default_currency: str
    branding: dict[str, Any]
    settings: dict[str, Any]
    created_at: datetime


# --- members & invitations -------------------------------------------------------------
class MemberOut(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    email: str
    display_name: str | None
    role: RoleName
    status: str
    all_projects: bool
    project_ids: list[uuid.UUID]
    accepted_at: datetime | None


class MemberUpdate(BaseModel):
    role: RoleName | None = None
    status: Literal["active", "suspended"] | None = None
    all_projects: bool | None = None
    project_ids: list[uuid.UUID] | None = None


class InvitationCreate(BaseModel):
    email: EmailStr
    role: RoleName
    all_projects: bool = True
    project_ids: list[uuid.UUID] = Field(default_factory=list)


class InvitationOut(BaseModel):
    id: uuid.UUID
    email: str
    role: RoleName
    project_ids: list[uuid.UUID]
    expires_at: datetime
    accepted: bool
    accept_url: str | None = Field(
        default=None, description="Only returned to the creator at creation time"
    )


class InvitationAccept(BaseModel):
    token: str = Field(min_length=20, max_length=200)


# --- projects --------------------------------------------------------------------------
class AreaDefinition(BaseModel):
    key: str = Field(pattern=r"^[a-z][a-z0-9_]{1,40}$")
    label: str
    description: str | None = None


class ProjectCreate(BaseModel):
    slug: str = Field(min_length=3, max_length=63)
    name: str = Field(min_length=1, max_length=200)
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    address: dict[str, Any] = Field(default_factory=dict)
    description: str | None = None
    area_definitions: list[AreaDefinition] = Field(
        default_factory=lambda: [
            AreaDefinition(key="net_internal", label="Net internal area"),
            AreaDefinition(key="gross_internal", label="Gross internal area"),
            AreaDefinition(key="balcony", label="Balcony / terrace"),
            AreaDefinition(key="total_sellable", label="Total sellable area"),
        ]
    )


class ProjectUpdate(BaseModel):
    name: str | None = None
    status: Literal["draft", "active", "archived"] | None = None
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    address: dict[str, Any] | None = None
    description: str | None = None
    code_pattern: str | None = Field(default=None, max_length=80)
    area_definitions: list[AreaDefinition] | None = None
    site_frame: dict[str, Any] | None = None
    regulatory: dict[str, Any] | None = None
    version: int = Field(description="Optimistic concurrency: current version")


class ProjectOut(ORM):
    id: uuid.UUID
    tenant_id: uuid.UUID
    slug: str
    name: str
    status: str
    currency: str
    address: dict[str, Any]
    description: str | None
    code_pattern: str
    area_definitions: list[Any]
    site_frame: dict[str, Any]
    regulatory: dict[str, Any]
    version: int
    created_at: datetime
    updated_at: datetime


class BuildingCreate(BaseModel):
    code: str = Field(min_length=1, max_length=20, pattern=r"^[A-Za-z0-9][A-Za-z0-9.-]{0,19}$")
    name: str | None = None
    kind: Literal["building", "site"] = "building"
    sort_order: int = 0


class BuildingUpdate(BaseModel):
    name: str | None = None
    site_transform: dict[str, Any] | None = None
    placement_status: Literal["unplaced", "draft", "confirmed"] | None = None
    sort_order: int | None = None
    version: int


class FloorIn(BaseModel):
    level: int
    display_name: str = Field(min_length=1, max_length=80)
    height_m: Decimal | None = None
    elevation_m: Decimal | None = None


class FloorsBulkCreate(BaseModel):
    floors: list[FloorIn] = Field(min_length=1, max_length=200)


class FloorOut(ORM):
    id: uuid.UUID
    building_id: uuid.UUID
    level: int
    display_name: str
    height_m: Decimal | None
    elevation_m: Decimal | None
    sort_order: int
    version: int


class BuildingOut(ORM):
    id: uuid.UUID
    project_id: uuid.UUID
    code: str
    name: str | None
    kind: str
    site_transform: dict[str, Any]
    placement_status: str
    sort_order: int
    version: int
    floors: list[FloorOut] = Field(default_factory=list)


class SiteFeatureCreate(BaseModel):
    kind: Literal["garden", "road", "parking_zone", "amenity", "common_area", "entrance", "other"]
    name: str = Field(min_length=1, max_length=200)
    polygon: dict[str, Any] | None = None
    is_public: bool = True
    sort_order: int = 0


class SiteFeatureOut(ORM):
    id: uuid.UUID
    project_id: uuid.UUID
    kind: str
    name: str
    polygon: dict[str, Any] | None
    is_public: bool
    sort_order: int


class AuditOut(ORM):
    id: uuid.UUID
    actor_user_id: uuid.UUID | None
    actor_role: str | None
    entity_type: str
    entity_id: uuid.UUID | None
    action: str
    before: dict[str, Any] | None
    after: dict[str, Any] | None
    at: datetime


class AuditPage(BaseModel):
    items: list[AuditOut]
    total: int
