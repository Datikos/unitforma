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


# --- documents ---------------------------------------------------------------------------
DocumentKind = Literal[
    "site_plan",
    "floor_plan",
    "section",
    "elevation",
    "render",
    "schedule",
    "model_ifc",
    "model_glb",
    "texture",
    "permit",
    "other",
]


class DocumentCreate(BaseModel):
    kind: DocumentKind
    title: str = Field(min_length=1, max_length=200)
    building_id: uuid.UUID | None = None
    visibility: Literal["internal", "public"] = "internal"
    source: dict[str, Any] = Field(default_factory=dict)


class RevisionOut(ORM):
    id: uuid.UUID
    document_id: uuid.UUID
    revision_no: int
    file_name: str
    mime: str | None
    byte_size: int | None
    sha256: str | None
    page_count: int | None
    source_note: str | None
    processing_status: str
    processing_error: str | None
    created_at: datetime


class DocumentOut(ORM):
    id: uuid.UUID
    project_id: uuid.UUID
    building_id: uuid.UUID | None
    kind: str
    title: str
    visibility: str
    current_revision_id: uuid.UUID | None
    source: dict[str, Any]
    created_at: datetime
    current_revision: RevisionOut | None = None


class UploadIntentCreate(BaseModel):
    file_name: str = Field(min_length=1, max_length=255)
    content_type: str = Field(min_length=3, max_length=120)
    byte_size: int = Field(gt=0)
    source_note: str | None = Field(default=None, max_length=500)


class UploadIntentOut(BaseModel):
    revision: RevisionOut
    upload_url: str
    method: Literal["PUT"] = "PUT"
    headers: dict[str, str]


class Calibration(BaseModel):
    p1: list[float] = Field(min_length=2, max_length=2)
    p2: list[float] = Field(min_length=2, max_length=2)
    distance_m: float = Field(gt=0)


class SheetOut(ORM):
    id: uuid.UUID
    revision_id: uuid.UUID
    page_no: int
    width_pt: Decimal | None
    height_pt: Decimal | None
    raster_width: int | None
    raster_height: int | None
    floor_id: uuid.UUID | None
    suggested_floor_id: uuid.UUID | None
    assignment_status: str
    calibration: dict[str, Any] | None
    calibration_status: str
    hints: dict[str, Any]
    version: int
    raster_url: str | None = None
    thumbnail_url: str | None = None
    extract_url: str | None = None


class SheetAssign(BaseModel):
    floor_id: uuid.UUID | None
    version: int


class SheetCalibrate(BaseModel):
    calibration: Calibration
    version: int


# --- units & mapping ----------------------------------------------------------------------
Ring = list[list[float]]


class BoundaryCreate(BaseModel):
    ring: Ring = Field(min_length=3, max_length=500)
    unit_type: Literal["apartment", "commercial", "parking", "storage"] = "apartment"
    code: str | None = Field(default=None, max_length=40)
    label: str | None = Field(default=None, max_length=80)


class BoundaryUpdate(BaseModel):
    ring: Ring = Field(min_length=3, max_length=500)
    version: int


class AreaOut(ORM):
    id: uuid.UUID
    area_type: str
    value_m2: Decimal
    source: str
    verification_status: str
    is_current: bool


class BoundaryOut(ORM):
    id: uuid.UUID
    unit_id: uuid.UUID
    sheet_id: uuid.UUID
    polygon: dict[str, Any]
    polygon_m: dict[str, Any] | None
    source: str
    status: str
    is_current: bool
    label: str | None
    version: int


class UnitOut(ORM):
    id: uuid.UUID
    project_id: uuid.UUID
    building_id: uuid.UUID
    floor_id: uuid.UUID
    code: str
    unit_type: str
    lifecycle_status: str
    verification_status: str
    publication_status: str
    rooms: int | None
    bedrooms: int | None
    bathrooms: int | None
    version: int
    areas: list[AreaOut] = Field(default_factory=list)
    boundaries: list[BoundaryOut] = Field(default_factory=list)


class UnitCreated(BaseModel):
    unit: UnitOut
    boundary: BoundaryOut


class UnitRelabel(BaseModel):
    code: str = Field(min_length=1, max_length=40)
    version: int
    reason: str | None = None


class UnitRemove(BaseModel):
    version: int
    note: str | None = None


class UnitMerge(BaseModel):
    survivor_id: uuid.UUID
    absorbed_ids: list[uuid.UUID] = Field(min_length=1)
    sheet_id: uuid.UUID | None = None
    ring: Ring | None = None
    note: str | None = None


class UnitSplit(BaseModel):
    sheet_id: uuid.UUID
    rings: list[Ring] = Field(min_length=2, max_length=20)
    codes: list[str | None] = Field(default_factory=list)
    note: str | None = None


class AreaSet(BaseModel):
    area_type: str = Field(pattern=r"^[a-z][a-z0-9_]{1,40}$")
    value_m2: Decimal = Field(ge=0)
    verified: bool = False


class LineageOut(ORM):
    id: uuid.UUID
    event_type: str
    revision_id: uuid.UUID | None
    from_unit_ids: list[uuid.UUID]
    to_unit_ids: list[uuid.UUID]
    decided_by: uuid.UUID | None
    decided_at: datetime
    note: str | None


class CodeHistoryOut(ORM):
    old_code: str | None
    new_code: str
    changed_at: datetime
    reason: str | None
