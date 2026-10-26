"""Pydantic request/response models for the admin and platform APIs."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

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


class ApiTokenCreate(BaseModel):
    """A personal API token for MCP assistants and scripts (ADR-0015 Decision 2)."""

    name: str = Field(min_length=1, max_length=120)
    scope: Literal["read", "write"] = "read"
    expires_in_days: int = Field(default=90, ge=1, le=365)


class ApiTokenOut(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    user_email: str
    name: str
    token_prefix: str
    scope: str
    status: Literal["active", "expired", "revoked"]
    expires_at: datetime
    last_used_at: datetime | None
    revoked_at: datetime | None
    created_at: datetime


class ApiTokenCreated(ApiTokenOut):
    """The secret is in this response only; it is never stored or shown again."""

    secret: str


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
    portal_settings: PortalSettings | None = None
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
    sales_settings: dict[str, Any] = Field(default_factory=dict)
    portal_settings: dict[str, Any] = Field(default_factory=dict)
    version: int
    created_at: datetime
    updated_at: datetime


class BuildingCreate(BaseModel):
    code: str = Field(min_length=1, max_length=20, pattern=r"^[A-Za-z0-9][A-Za-z0-9.-]{0,19}$")
    name: str | None = None
    kind: Literal["building", "site"] = "building"
    sort_order: int = 0


class SiteTransform(BaseModel):
    """Building local frame → site frame (metres, plan §3.5)."""

    tx: float = 0.0
    ty: float = 0.0
    rotation_deg: float = Field(default=0.0, ge=-360, le=360)
    scale: float = Field(default=1.0, gt=0.01, lt=100)
    elevation: float = 0.0


ConstructionStatus = Literal["planned", "under_construction", "completed"]


class FacadeAssignIn(BaseModel):
    """One elevation drawing on one side of the building's rectangle (ADR-0016 Decision 2)."""

    side: int = Field(ge=0, le=3, description="Side index: clockwise on the sheet from the top")
    sheet_id: uuid.UUID
    region: dict[str, Any] | None = Field(
        default=None, description='{"ring": [[x, y], ...]} normalised to the sheet'
    )
    flip: bool = False


class BuildingUpdate(BaseModel):
    """Fields left out are kept; ``name``, ``construction_status``, ``completion``, ``terms`` and
    ``elevation_sheet_id`` sent as null are cleared (ADR-0014 Decision 3)."""

    name: str | None = Field(default=None, max_length=200)
    site_transform: SiteTransform | None = None
    placement_status: Literal["unplaced", "draft", "confirmed"] | None = None
    sort_order: int | None = None
    construction_status: ConstructionStatus | None = None
    completion: str | None = Field(default=None, max_length=80)
    terms: str | None = Field(default=None, max_length=4000)
    elevation_sheet_id: uuid.UUID | None = None
    facades: list[FacadeAssignIn] | None = Field(
        default=None, max_length=4, description="All sides at once; [] clears them (ADR-0016 E3)"
    )
    version: int


class FloorIn(BaseModel):
    level: int
    display_name: str = Field(min_length=1, max_length=80)
    height_m: Decimal | None = None
    elevation_m: Decimal | None = None


class FloorsBulkCreate(BaseModel):
    floors: list[FloorIn] = Field(min_length=1, max_length=200)


class ProposedFloorOut(BaseModel):
    """A storey read from the drawings' level markers (ADR-0010)."""

    level: int
    display_name: str
    elevation_m: float
    height_m: float | None
    status: Literal["new", "update", "existing"]
    floor_id: uuid.UUID | None
    sheets: int
    markers: list[str]


class BlockProposalOut(BaseModel):
    """A split-level block drawn beside the others on the sheets (ADR-0014)."""

    code: str
    column_x: float
    sheets: int
    floors: list[ProposedFloorOut]
    roof: dict[str, Any]


class FloorProposalOut(BaseModel):
    building_id: uuid.UUID
    sheets_with_markers: int
    floors: list[ProposedFloorOut]
    unmatched_existing: list[dict[str, Any]]
    roof: dict[str, Any]
    counts: dict[str, int]
    split_level: bool = False
    blocks: list[BlockProposalOut] = Field(default_factory=list)


class BlockAccept(BaseModel):
    code: str = Field(min_length=1, max_length=20, pattern=r"^[A-Za-z0-9][A-Za-z0-9.-]{0,19}$")
    name: str | None = Field(default=None, max_length=200)
    floors: list[FloorIn] = Field(min_length=1, max_length=200)


class BlocksAcceptIn(BaseModel):
    blocks: list[BlockAccept] = Field(min_length=1, max_length=8)
    delete_source: bool = False


class BlocksAcceptOut(BaseModel):
    buildings: list[BuildingOut]
    source_removed: bool


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
    construction_status: str | None = None
    completion: str | None = None
    terms: str | None = None
    elevation_sheet_id: uuid.UUID | None = None
    sort_order: int
    version: int
    facades: list[dict[str, Any]] = Field(default_factory=list)
    floors: list[FloorOut] = Field(default_factory=list)

    @field_validator("facades", mode="before")
    @classmethod
    def _facade_items(cls, v: Any) -> list[dict[str, Any]]:
        """The column holds {"v": 1, "items": [...]}; the API shows the items."""
        if isinstance(v, dict):
            return list(v.get("items") or [])
        return list(v or [])


class ElevationCandidateOut(BaseModel):
    """A current sheet with stacked level markers (a section or an elevation) that can become the
    building's elevation floor picker (ADR-0014 Decision 1)."""

    sheet_id: uuid.UUID
    document_title: str
    document_kind: str
    page_no: int
    markers: int
    matched_floors: int
    floors: int
    raster_url: str | None = None
    thumbnail_url: str | None = None


class SiteFeatureCreate(BaseModel):
    kind: Literal["garden", "road", "parking_zone", "amenity", "common_area", "entrance", "other"]
    name: str = Field(min_length=1, max_length=200)
    polygon: dict[str, Any] | None = None
    is_public: bool = True
    sort_order: int = 0


class SiteFeatureUpdate(BaseModel):
    kind: (
        Literal["garden", "road", "parking_zone", "amenity", "common_area", "entrance", "other"]
        | None
    ) = None
    name: str | None = Field(default=None, min_length=1, max_length=200)
    polygon: dict[str, Any] | None = None
    clear_polygon: bool = False
    is_public: bool | None = None
    sort_order: int | None = None


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
    "unclassified",
]


class DocumentCreate(BaseModel):
    kind: DocumentKind = Field(
        default="unclassified",
        description="Omit to let the platform classify from the title and, later, the content",
    )
    title: str = Field(min_length=1, max_length=200)
    building_id: uuid.UUID | None = None
    visibility: Literal["internal", "public"] = "internal"
    source: dict[str, Any] = Field(default_factory=dict)


class DocumentUpdate(BaseModel):
    """Kind set here is final: the worker never replaces a kind a person chose (ADR-0008)."""

    kind: DocumentKind | None = None
    title: str | None = Field(default=None, min_length=1, max_length=200)
    building_id: uuid.UUID | None = None
    clear_building: bool = False
    # ``public`` render documents form the portal gallery (ADR-0016 Decision 1)
    visibility: Literal["internal", "public"] | None = None


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
    kind_source: str = "manual"
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


Ring = list[list[float]]


class SheetFloorOut(ORM):
    floor_id: uuid.UUID
    status: Literal["suggested", "confirmed"]
    source: str
    region: dict[str, Any] | None
    marker: str | None


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
    floors: list[SheetFloorOut] = Field(default_factory=list)
    excluded: bool = False
    exclusion_reason: str | None = None


class SheetExclude(BaseModel):
    excluded: bool
    reason: str | None = Field(default=None, max_length=200)
    version: int


class PagesExclude(BaseModel):
    """Exclude or include pages of a revision at once (e.g. a fire-safety set, pages 12–51)."""

    pages: list[int] = Field(min_length=1, max_length=2000)
    excluded: bool
    reason: str | None = Field(default=None, max_length=200)


class SheetAssign(BaseModel):
    floor_id: uuid.UUID | None
    version: int


class FloorRegion(BaseModel):
    ring: Ring = Field(min_length=3, max_length=200)


class SheetFloorIn(BaseModel):
    floor_id: uuid.UUID
    region: FloorRegion | None = None


class SheetFloorsSet(BaseModel):
    """All floors the sheet shows; replaces the current set (empty = the sheet shows none)."""

    floors: list[SheetFloorIn] = Field(max_length=20)
    version: int


class SheetCalibrate(BaseModel):
    calibration: Calibration
    version: int


# --- units & mapping ----------------------------------------------------------------------


class BoundaryCreate(BaseModel):
    ring: Ring = Field(min_length=3, max_length=500)
    # on a sheet showing several floors; default: the floor whose region holds the outline
    floor_id: uuid.UUID | None = None
    # the area printed with the label on the drawing → documented area (drawing_schedule)
    printed_area_m2: Decimal | None = Field(default=None, gt=0, le=100000)
    unit_type: Literal["apartment", "commercial", "parking", "storage"] = "apartment"
    code: str | None = Field(default=None, max_length=40)
    label: str | None = Field(default=None, max_length=80)
    source: Literal["manual", "vector_suggest", "raster_suggest"] = "manual"


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


# --- suggestions & revision diff proposals (plan §13.2, §13.3) ---------------------------
class SuggestionOut(BaseModel):
    ring: Ring
    label: str | None
    text: str
    confidence: float
    area_norm: float
    source: str = "vector_suggest"
    method: Literal["fill", "grown", "loop"] = "loop"
    printed_area_m2: float | None = None
    measured_area_m2: float | None = None
    floor_id: uuid.UUID | None = None
    unit_type: Literal["apartment", "commercial", "storage", "parking"] | None = None


class PrintedAreasOut(BaseModel):
    updated: int
    unchanged: int
    unmatched: int


class ProposalItemOut(ORM):
    id: uuid.UUID
    kind: str
    old_unit_ids: list[uuid.UUID]
    old_boundary_ids: list[uuid.UUID]
    old_sheet_id: uuid.UUID | None
    new_sheet_id: uuid.UUID | None
    new_rings: list[Ring]
    labels: list[str | None]
    overlaps: list[list[Any]]
    confidence: Decimal
    decision: str
    decided_at: datetime | None
    result: dict[str, Any]


class ProposalOut(ORM):
    id: uuid.UUID
    project_id: uuid.UUID
    document_id: uuid.UUID
    old_revision_id: uuid.UUID | None
    new_revision_id: uuid.UUID
    status: str
    summary: dict[str, Any]
    created_at: datetime
    resolved_at: datetime | None
    items: list[ProposalItemOut] = Field(default_factory=list)


class ProposalDecide(BaseModel):
    decision: Literal["accept", "reject"]
    code: str | None = Field(default=None, max_length=40, description="new/relabelled: unit code")
    codes: list[str | None] | None = Field(
        default=None, description="split: code per new ring (inheriting ring keeps its code)"
    )
    unit_type: Literal["apartment", "commercial", "parking", "storage"] | None = None
    survivor_id: uuid.UUID | None = Field(default=None, description="merged: unit that keeps id")
    inherit_index: int | None = Field(default=None, description="split: ring that keeps the id")
    note: str | None = Field(default=None, max_length=500)


class ProposalAcceptAll(BaseModel):
    kinds: list[Literal["matched", "relabelled", "new", "missing", "split", "merged"]] = Field(
        default_factory=lambda: ["matched"]
    )


# --- geometry (plan §11.3) ----------------------------------------------------------------
class FootprintOut(BaseModel):
    building_id: uuid.UUID
    code: str
    name: str | None
    placement_status: str
    site_transform: dict[str, Any]
    version: int
    ring_m: Ring | None
    source_floor_level: int | None
    floors: int
    height_m: float
    sides: list[dict[str, Any]] | None = None
    facades: list[dict[str, Any]] = Field(default_factory=list)


class MassingOut(ORM):
    id: uuid.UUID
    project_id: uuid.UUID
    kind: str
    status: str
    stats: dict[str, Any]
    error: str | None
    created_at: datetime
    glb_url: str | None = None


# --- sales workspace (plan §6) ------------------------------------------------------------
Availability = Literal["available", "reserved", "sold", "withdrawn"]
PublicFieldKey = Literal[
    "list_price", "payment_plan", "promotions", "description", "areas", "rooms", "media"
]


class InventoryRow(BaseModel):
    unit_id: uuid.UUID
    code: str
    building_id: uuid.UUID
    building_code: str
    floor_id: uuid.UUID
    floor_level: int
    floor_name: str
    unit_type: str
    lifecycle_status: str
    verification_status: str
    publication_status: str
    availability: Availability
    availability_reason: str | None
    availability_changed_at: datetime | None
    list_price: Decimal | None = Field(description="NULL = price unknown / on request")
    currency: str
    price_on_request: bool
    price_area_type: str = Field(description="Effective area type the price per m² uses")
    price_area_type_override: str | None
    price_area_m2: Decimal | None
    price_area_source: str | None
    price_area_verified: bool
    price_per_m2: Decimal | None = Field(description="Computed on read, never stored")
    payment_plan_id: uuid.UUID | None
    payment_plan_name: str | None
    promotion_ids: list[uuid.UUID]
    promotion_names: list[str]
    rooms: int | None
    bedrooms: int | None
    bathrooms: int | None
    orientation: str | None
    entrance: str | None = Field(default=None, description="Staircase; public like the floor")
    layout: str | None = Field(
        default=None, description="Code of the unit's layout in the project registry (ADR-0022)"
    )
    layout_id: uuid.UUID | None = None
    layout_name: str | None = None
    wall_colour: str | None = Field(
        default=None, description="Wall finish: a RAL code or a hex colour, shown to buyers"
    )
    public_description: str | None
    internal_notes: str | None
    public_fields: dict[str, bool]
    public_field_overrides: dict[str, bool]
    areas: dict[str, Decimal]
    media_count: int = Field(description="The unit's own ready media; layout media not counted")
    version: int = Field(description="Sales row version; 0 = no sales data entered yet")
    updated_at: datetime | None


class SalesChanges(BaseModel):
    """Only the fields present in the request are changed; an explicit null clears a value."""

    availability: Availability | None = None
    availability_reason: str | None = Field(default=None, max_length=2000)
    list_price: Decimal | None = Field(default=None, ge=0, max_digits=14, decimal_places=2)
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    price_on_request: bool | None = None
    price_area_type: str | None = Field(default=None, max_length=40)
    payment_plan_id: uuid.UUID | None = None
    promotion_ids: list[uuid.UUID] | None = None
    public_description: str | None = Field(default=None, max_length=4000)
    internal_notes: str | None = Field(default=None, max_length=4000)
    rooms: int | None = Field(default=None, ge=0, le=100)
    bedrooms: int | None = Field(default=None, ge=0, le=100)
    bathrooms: int | None = Field(default=None, ge=0, le=100)
    orientation: str | None = Field(default=None, max_length=20)
    entrance: str | None = Field(default=None, max_length=20)
    layout: str | None = Field(
        default=None, max_length=40, description="A code from the layout registry; null unlinks"
    )
    wall_colour: str | None = Field(default=None, max_length=40)
    public_fields: dict[PublicFieldKey, bool] | None = None


class SalesUpdate(SalesChanges):
    version: int | None = Field(
        default=None, description="Version you edited; or send it as the If-Match header"
    )
    reason: str | None = Field(default=None, max_length=500)
    confirm_zero_price: bool = False


class BulkItem(BaseModel):
    unit_id: uuid.UUID
    version: int


class BulkUpdate(BaseModel):
    items: list[BulkItem] = Field(min_length=1, max_length=5000)
    changes: SalesChanges = Field(default_factory=SalesChanges)
    price_adjust_percent: Decimal | None = Field(
        default=None,
        ge=-90,
        le=1000,
        description="Multiply existing prices; empty prices stay empty",
    )
    preview: bool = True
    reason: str | None = Field(default=None, max_length=500)
    confirm_zero_price: bool = False


class BulkUnitResult(BaseModel):
    unit_id: uuid.UUID
    code: str
    changes: list[dict[str, Any]]


class BulkResult(BaseModel):
    preview: bool
    units: list[BulkUnitResult]
    changed_units: int


class SalesSettingsIn(BaseModel):
    price_area_type: str | None = None
    public_fields: dict[PublicFieldKey, bool] | None = None
    version: int = Field(description="Project version")


class SalesSettingsOut(BaseModel):
    price_area_type: str
    public_fields: dict[str, bool]
    import_mapping: dict[str, str]
    import_options: dict[str, Any]
    area_definitions: list[Any]
    project_version: int


class Milestone(BaseModel):
    label: str = Field(min_length=1, max_length=120)
    percent: Decimal = Field(gt=0, le=100, decimal_places=2)
    due: str | None = Field(default=None, max_length=120, description="e.g. 'on signing'")


class PaymentPlanIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=4000)
    schedule: list[Milestone] = Field(default_factory=list, max_length=40)
    is_public: bool = True
    is_active: bool = True
    sort_order: int = 0


class PaymentPlanUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=4000)
    schedule: list[Milestone] | None = Field(default=None, max_length=40)
    is_public: bool | None = None
    is_active: bool | None = None
    sort_order: int | None = None
    version: int


class PaymentPlanOut(ORM):
    id: uuid.UUID
    project_id: uuid.UUID
    name: str
    description: str | None
    schedule: list[dict[str, Any]]
    is_public: bool
    is_active: bool
    sort_order: int
    version: int


PromotionKind = Literal["discount_percent", "discount_amount", "gift", "financing", "other"]


class PromotionIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    kind: PromotionKind = "other"
    value: Decimal | None = Field(default=None, ge=0, max_digits=14, decimal_places=2)
    terms: str | None = Field(default=None, max_length=4000)
    valid_from: date | None = None
    valid_to: date | None = None
    is_public: bool = True
    is_active: bool = True


class PromotionUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    kind: PromotionKind | None = None
    value: Decimal | None = Field(default=None, ge=0, max_digits=14, decimal_places=2)
    terms: str | None = Field(default=None, max_length=4000)
    valid_from: date | None = None
    valid_to: date | None = None
    is_public: bool | None = None
    is_active: bool | None = None
    version: int


class PromotionOut(ORM):
    id: uuid.UUID
    project_id: uuid.UUID
    name: str
    kind: str
    value: Decimal | None
    terms: str | None
    valid_from: date | None
    valid_to: date | None
    is_public: bool
    is_active: bool
    version: int


MediaKind = Literal[
    "plan_render", "interior_render", "exterior_render", "photo", "video", "document"
]


class MediaCreate(BaseModel):
    file_name: str = Field(min_length=1, max_length=255)
    content_type: str = Field(min_length=3, max_length=120)
    byte_size: int = Field(gt=0)
    kind: MediaKind = "photo"
    is_public: bool = False
    alt_text: str | None = Field(default=None, max_length=300)
    is_ai_generated: bool = False
    ai_disclosure_text: str | None = Field(default=None, max_length=300)


class MediaUpdate(BaseModel):
    kind: MediaKind | None = None
    is_public: bool | None = None
    alt_text: str | None = Field(default=None, max_length=300)
    is_ai_generated: bool | None = None
    ai_disclosure_text: str | None = Field(default=None, max_length=300)
    version: int


class MediaOut(ORM):
    id: uuid.UUID
    unit_id: uuid.UUID | None = Field(default=None, description="Owner, or null for layout media")
    layout_id: uuid.UUID | None = Field(default=None, description="Owner when a layout's media")
    kind: str
    file_name: str
    mime: str
    byte_size: int | None
    status: str
    sort_order: int
    is_public: bool
    alt_text: str | None
    is_ai_generated: bool
    ai_disclosure_text: str | None
    version: int
    created_at: datetime
    url: str | None = None


class MediaIntentOut(BaseModel):
    media: MediaOut
    upload_url: str
    method: Literal["PUT"] = "PUT"
    headers: dict[str, str]


class MediaOrder(BaseModel):
    ids: list[uuid.UUID] = Field(min_length=1, max_length=500)


# --- layout registry (ADR-0022) ------------------------------------------------------------------
class LayoutIn(BaseModel):
    code: str = Field(min_length=1, max_length=40, description="Unique per project, without case")
    name: str | None = Field(default=None, max_length=120)


class LayoutUpdate(BaseModel):
    code: str | None = Field(default=None, min_length=1, max_length=40)
    name: str | None = Field(default=None, max_length=120)
    version: int


class LayoutUnitOut(BaseModel):
    unit_id: uuid.UUID
    code: str
    availability: str
    building_code: str
    floor_level: int


class LayoutOut(ORM):
    id: uuid.UUID
    project_id: uuid.UUID
    code: str
    name: str | None
    version: int
    created_at: datetime
    updated_at: datetime
    units: list[LayoutUnitOut] = Field(description="Linked units by code")
    media_count: int
    public_media_count: int
    cover_url: str | None = Field(description="Signed URL of the first public image, or null")


class LayoutRenderRequest(BaseModel):
    note: str | None = Field(default=None, max_length=500)
    unit_id: uuid.UUID | None = Field(
        default=None,
        description="The member whose outline is cropped; default: the first by code with one",
    )


class PriceHistoryOut(ORM):
    id: uuid.UUID
    old_price: Decimal | None
    new_price: Decimal | None
    old_currency: str | None
    new_currency: str | None
    changed_by: uuid.UUID | None
    changed_at: datetime
    reason: str | None
    import_batch_id: uuid.UUID | None


class AvailabilityHistoryOut(ORM):
    id: uuid.UUID
    old_availability: str | None
    new_availability: str
    changed_by: uuid.UUID | None
    changed_at: datetime
    reason: str | None
    import_batch_id: uuid.UUID | None


class SalesHistoryOut(BaseModel):
    prices: list[PriceHistoryOut]
    availability: list[AvailabilityHistoryOut]
    audit: list[AuditOut]


class ImportOptions(BaseModel):
    decimal_separator: Literal[".", ","] = "."
    thousands_separator: Literal["", ",", ".", " ", "'"] = ""
    confirm_zero_price: bool = Field(
        default=False,
        description="Accept price 0 on rows whose price_on_request column is explicitly false",
    )


class ImportDryRun(BaseModel):
    mapping: dict[str, str] = Field(description="import field → column header")
    options: ImportOptions = Field(default_factory=ImportOptions)


class ImportApply(BaseModel):
    skip_invalid_rows: bool = False


class ImportBatchOut(ORM):
    id: uuid.UUID
    project_id: uuid.UUID
    file_name: str
    file_format: str
    status: str
    headers: list[str]
    mapping: dict[str, str]
    options: dict[str, Any]
    report: dict[str, Any]
    row_count: int
    change_count: int
    error_count: int
    created_at: datetime
    applied_at: datetime | None
    targets: list[str] = Field(default_factory=list)


# --- publishing (plan §9.3) -----------------------------------------------------------------
HexColor = Annotated[str, Field(pattern=r"^#[0-9a-fA-F]{6}$")]


class Branding(BaseModel):
    """Allow-listed branding keys; anything else is dropped by the snapshot builder."""

    primary_color: HexColor | None = None
    accent_color: HexColor | None = None
    display_name: str | None = Field(default=None, max_length=120)
    tagline: str | None = Field(default=None, max_length=200)
    contact_email: EmailStr | None = None
    contact_phone: str | None = Field(default=None, max_length=50)
    website: str | None = Field(default=None, max_length=200, pattern=r"^https://")
    legal_text: str | None = Field(default=None, max_length=4000)


class PortalSettings(BaseModel):
    hero_text: str | None = Field(default=None, max_length=2000)
    construction_stage: str | None = Field(default=None, max_length=80)
    completion: str | None = Field(default=None, max_length=80)
    price_note: str | None = Field(
        default=None, max_length=200, description="Printed next to every price (ADR-0014)"
    )
    terms: str | None = Field(
        default=None, max_length=4000, description="Default terms for buildings without their own"
    )
    branding: Branding | None = None


class PublicationOut(ORM):
    id: uuid.UUID
    project_id: uuid.UUID
    version_no: int
    status: str
    summary: dict[str, Any]
    published_at: datetime | None
    retired_at: datetime | None
    created_at: datetime


class PublishRequest(BaseModel):
    mode: Literal["preview", "publish"] = "preview"


class PublishResult(BaseModel):
    publication: PublicationOut
    portal_url: str | None
    preview_url: str | None = None
    preview_token: str | None = None


class ReadinessItem(BaseModel):
    key: str
    level: Literal["ok", "warning", "error"]
    message: str
    count: int | None = None


class ReadinessOut(BaseModel):
    ok: bool
    items: list[ReadinessItem]
    published_version: int | None
    portal_url: str | None
    unit_counts: dict[str, int] = Field(default_factory=dict)


class UnitPublicationIn(BaseModel):
    status: Literal["unpublished", "published", "hidden"]
    unit_ids: list[uuid.UUID] | None = Field(default=None, max_length=10000)
    all_active: bool = Field(default=False, description="Apply to every approved (active) unit")


class UnitPublicationOut(BaseModel):
    changed: int
    unit_counts: dict[str, int]


# --- regulatory (ADR-0007) --------------------------------------------------------------
class PermitReference(BaseModel):
    reference: str = Field(
        min_length=1,
        max_length=500,
        description="tas.ge public page address or the bare document id",
    )


class PermitImportCreate(PermitReference):
    slug: str | None = Field(default=None, min_length=3, max_length=63)
    name: str | None = Field(default=None, min_length=1, max_length=200)
    building_code: str | None = Field(
        default=None, min_length=1, max_length=20, pattern=r"^[A-Za-z0-9][A-Za-z0-9.-]{0,19}$"
    )


class PermitAttachmentOut(BaseModel):
    attached_file_id: int
    fieldset_id: int | None
    fieldset: str
    file_name: str
    extension: str
    uploaded_at: str | None
    download_url: str
    kind: str
    skip_reason: str | None


class PermitPreviewOut(BaseModel):
    source: dict[str, Any]
    permit: dict[str, Any]
    nomenclature: dict[str, Any]
    class_calculator: list[dict[str, Any]]
    parcels: list[dict[str, Any]]
    technical_indicators: list[dict[str, Any]]
    heights: dict[str, float | None]
    suggestions: dict[str, str]
    attachments: list[PermitAttachmentOut]
    counts: dict[str, int]


class RegulatoryImportOut(ORM):
    id: uuid.UUID
    project_id: uuid.UUID
    source: str
    external_id: str
    status: str
    requested_by: uuid.UUID | None
    started_at: datetime | None
    finished_at: datetime | None
    stats: dict[str, Any]
    error: str | None
    created_at: datetime
    permit: dict[str, Any] = Field(default_factory=dict)
    counts: dict[str, int] = Field(default_factory=dict)


class PermitImportResult(BaseModel):
    project: ProjectOut
    building: BuildingOut
    job: RegulatoryImportOut


# --- IFC models and space links (ADR-0006 Phase C) -----------------------------------------
class IfcSpaceLinkOut(ORM):
    id: uuid.UUID
    building_id: uuid.UUID
    geometry_model_id: uuid.UUID
    ifc_global_id: str
    name: str | None
    long_name: str | None
    storey_name: str | None
    storey_elevation_m: Decimal | None
    floor_id: uuid.UUID | None
    unit_id: uuid.UUID | None
    status: str
    confidence: Decimal | None
    areas: dict[str, Any]
    unit_code: str | None = None
    floor_level: int | None = None


class IfcSpaceLinkDecide(BaseModel):
    """Confirm a space as a unit (optionally another unit than suggested) or reject it."""

    decision: Literal["confirm", "reject", "reset"]
    unit_id: uuid.UUID | None = None


class BuildingModelOut(ORM):
    """The current IFC-derived model of a building (kind ``ifc``), if any."""

    id: uuid.UUID
    building_id: uuid.UUID | None
    kind: str
    status: str
    stats: dict[str, Any]
    error: str | None
    created_at: datetime
    glb_url: str | None = None
    links: dict[str, int] = Field(default_factory=dict)


# --- AI-generated 3D plan renders (ADR-0017 Decision 3) -------------------------------------------
class RenderRequest(BaseModel):
    note: str | None = Field(
        default=None,
        max_length=500,
        description="Extra instructions appended to the fixed prompt (style, finishes)",
    )
    with_unit_id: uuid.UUID | None = Field(
        default=None,
        description="A neighbouring unit on the same floor to show joined into one apartment",
    )


class RenderOut(ORM):
    id: uuid.UUID
    unit_id: uuid.UUID
    status: str
    provider: str
    model: str
    note: str | None
    error: str | None
    cost_usd: Decimal | None
    media_id: uuid.UUID | None
    partner_unit_id: uuid.UUID | None = None
    partner_code: str | None = None
    layout_id: uuid.UUID | None = Field(default=None, description="Set when the layout owns it")
    source_code: str | None = Field(default=None, description="Unit whose outline was cropped")
    requested_by: uuid.UUID | None
    reviewed_by: uuid.UUID | None
    created_at: datetime
    finished_at: datetime | None
    reviewed_at: datetime | None
    url: str | None = None  # presigned preview of the generated image while it exists


class RendersOut(BaseModel):
    enabled: bool
    provider: str
    model: str
    daily_limit: int
    used_today: int
    cost_per_image_usd: float | None
    items: list[RenderOut]


# --- workspace render prompt (ADR-0023) ------------------------------------------------------
class RenderPromptOut(BaseModel):
    """The base text of every generated plan render: the workspace's own or the code default."""

    default: str
    prompt: str | None = Field(default=None, description="The workspace text; null = default")
    source: Literal["workspace", "default"]


class RenderPromptUpdate(BaseModel):
    prompt: str | None = Field(
        default=None, max_length=4000, description="null or blank clears the workspace text"
    )


# --- setup checklist (ADR-0017 Decision 5) -------------------------------------------------------
class SetupStepOut(BaseModel):
    key: str
    title: str
    status: Literal["done", "todo", "optional", "attention"]
    detail: str
    count: int | None = None
    link: str = Field(description="Admin screen that completes the step")


class SetupOut(BaseModel):
    done: int
    total: int
    steps: list[SetupStepOut]
