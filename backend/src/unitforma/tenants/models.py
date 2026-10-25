"""SQLAlchemy models for identity, tenancy and domains (plan §5.3, first slice).

Only the tables needed for Phase 0/1 are declared here. Every tenant-scoped table has
``tenant_id`` and is protected by RLS policies defined in the migrations.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from unitforma.core.ids import new_id


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Tenant(TimestampMixin, Base):
    __tablename__ = "tenants"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_id)
    slug: Mapped[str] = mapped_column(String(63), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(20), default="active")
    default_currency: Mapped[str] = mapped_column(String(3), default="EUR")
    branding: Mapped[dict] = mapped_column(JSONB, default=dict)
    settings: Mapped[dict] = mapped_column(JSONB, default=dict)


class User(TimestampMixin, Base):
    __tablename__ = "users"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_id)
    kratos_identity_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), unique=True)
    email: Mapped[str] = mapped_column(String(320), index=True)
    display_name: Mapped[str | None] = mapped_column(String(200))
    is_platform_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Membership(TimestampMixin, Base):
    __tablename__ = "memberships"
    __table_args__ = (UniqueConstraint("tenant_id", "user_id", name="uq_membership_tenant_user"),)
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_id)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    role: Mapped[str] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(20), default="invited")
    all_projects: Mapped[bool] = mapped_column(Boolean, default=True)
    invited_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class StaffInvitation(TimestampMixin, Base):
    __tablename__ = "staff_invitations"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_id)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), index=True
    )
    email: Mapped[str] = mapped_column(String(320))
    role: Mapped[str] = mapped_column(String(40))
    project_ids: Mapped[list[uuid.UUID]] = mapped_column(ARRAY(UUID(as_uuid=True)), default=list)
    token_hash: Mapped[str] = mapped_column(String(128), unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    accepted_membership_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))


class ReservedSubdomain(Base):
    __tablename__ = "reserved_subdomains"
    name: Mapped[str] = mapped_column(String(63), primary_key=True)


class PortalDomain(TimestampMixin, Base):
    __tablename__ = "portal_domains"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_id)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), index=True
    )
    project_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    hostname: Mapped[str] = mapped_column(String(253), unique=True)
    kind: Mapped[str] = mapped_column(String(30))  # platform_subdomain | custom
    verification_token: Mapped[str | None] = mapped_column(String(80))
    verification_status: Mapped[str] = mapped_column(String(20), default="pending")
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    tls_status: Mapped[str | None] = mapped_column(String(20))
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(20), default="active")  # active | disabled | removed
    removed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AuditLog(Base):
    __tablename__ = "audit_log"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_id)
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), index=True)
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    actor_role: Mapped[str | None] = mapped_column(String(40))
    entity_type: Mapped[str] = mapped_column(String(60))
    entity_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    action: Mapped[str] = mapped_column(String(40))
    before: Mapped[dict | None] = mapped_column(JSONB)
    after: Mapped[dict | None] = mapped_column(JSONB)
    request_id: Mapped[str | None] = mapped_column(Text)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class MembershipProjectAccess(Base):
    __tablename__ = "membership_project_access"
    __table_args__ = (UniqueConstraint("membership_id", "project_id", name="uq_mpa"),)
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_id)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), index=True
    )
    membership_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("memberships.id", ondelete="CASCADE"), index=True
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )


class Project(TimestampMixin, Base):
    __tablename__ = "projects"
    __table_args__ = (UniqueConstraint("tenant_id", "slug", name="uq_project_slug"),)
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_id)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), index=True
    )
    slug: Mapped[str] = mapped_column(String(63))
    name: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(20), default="draft")  # draft | active | archived
    currency: Mapped[str] = mapped_column(String(3), default="EUR")
    address: Mapped[dict] = mapped_column(JSONB, default=dict)
    code_pattern: Mapped[str] = mapped_column(String(80), default="{building}-{floor:02}-{seq:02}")
    area_definitions: Mapped[list] = mapped_column(JSONB, default=list)
    site_frame: Mapped[dict] = mapped_column(JSONB, default=dict)
    description: Mapped[str | None] = mapped_column(Text)
    regulatory: Mapped[dict] = mapped_column(JSONB, default=dict)
    version: Mapped[int] = mapped_column(default=1)


class Building(TimestampMixin, Base):
    __tablename__ = "buildings"
    __table_args__ = (UniqueConstraint("project_id", "code", name="uq_building_code"),)
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_id)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), index=True
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    code: Mapped[str] = mapped_column(String(20))
    name: Mapped[str | None] = mapped_column(String(200))
    kind: Mapped[str] = mapped_column(String(20), default="building")  # building | site
    site_transform: Mapped[dict] = mapped_column(JSONB, default=dict)
    placement_status: Mapped[str] = mapped_column(String(20), default="unplaced")
    sort_order: Mapped[int] = mapped_column(default=0)
    version: Mapped[int] = mapped_column(default=1)
    floors: Mapped[list[Floor]] = relationship(
        "Floor", order_by="Floor.level", cascade="all, delete-orphan", lazy="selectin"
    )


class Floor(TimestampMixin, Base):
    __tablename__ = "floors"
    __table_args__ = (UniqueConstraint("building_id", "level", name="uq_floor_level"),)
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_id)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), index=True
    )
    building_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("buildings.id", ondelete="CASCADE"), index=True
    )
    level: Mapped[int] = mapped_column()
    display_name: Mapped[str] = mapped_column(String(80))
    height_m: Mapped[float | None] = mapped_column(Numeric(6, 3))
    elevation_m: Mapped[float | None] = mapped_column(Numeric(8, 3))
    sort_order: Mapped[int] = mapped_column(default=0)
    version: Mapped[int] = mapped_column(default=1)


class SiteFeature(TimestampMixin, Base):
    __tablename__ = "site_features"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_id)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), index=True
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[str] = mapped_column(String(30))
    name: Mapped[str] = mapped_column(String(200))
    polygon: Mapped[dict | None] = mapped_column(JSONB)
    is_public: Mapped[bool] = mapped_column(Boolean, default=True)
    sort_order: Mapped[int] = mapped_column(default=0)


# --- documents and mapping (plan §5.3) -------------------------------------------------
class Document(TimestampMixin, Base):
    __tablename__ = "documents"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_id)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), index=True
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    building_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("buildings.id", ondelete="SET NULL")
    )
    kind: Mapped[str] = mapped_column(String(30))
    title: Mapped[str] = mapped_column(String(200))
    visibility: Mapped[str] = mapped_column(String(20), default="internal")
    current_revision_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    source: Mapped[dict] = mapped_column(JSONB, default=dict)


class DocumentRevision(TimestampMixin, Base):
    __tablename__ = "document_revisions"
    __table_args__ = (UniqueConstraint("document_id", "revision_no", name="uq_revision_no"),)
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_id)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), index=True
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), index=True
    )
    revision_no: Mapped[int] = mapped_column()
    object_key: Mapped[str] = mapped_column(String(512))
    file_name: Mapped[str] = mapped_column(String(255))
    mime: Mapped[str | None] = mapped_column(String(120))
    byte_size: Mapped[int | None] = mapped_column(BigInteger)
    sha256: Mapped[str | None] = mapped_column(String(64))
    page_count: Mapped[int | None] = mapped_column()
    uploaded_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    source_note: Mapped[str | None] = mapped_column(Text)
    processing_status: Mapped[str] = mapped_column(String(20), default="pending")
    processing_error: Mapped[str | None] = mapped_column(Text)
    supersedes_revision_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))


class Sheet(TimestampMixin, Base):
    __tablename__ = "sheets"
    __table_args__ = (UniqueConstraint("revision_id", "page_no", name="uq_sheet_page"),)
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_id)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), index=True
    )
    revision_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("document_revisions.id", ondelete="CASCADE"), index=True
    )
    page_no: Mapped[int] = mapped_column()
    width_pt: Mapped[float | None] = mapped_column(Numeric(10, 3))
    height_pt: Mapped[float | None] = mapped_column(Numeric(10, 3))
    raster_key: Mapped[str | None] = mapped_column(String(512))
    raster_width: Mapped[int | None] = mapped_column()
    raster_height: Mapped[int | None] = mapped_column()
    thumbnail_key: Mapped[str | None] = mapped_column(String(512))
    extract_key: Mapped[str | None] = mapped_column(String(512))
    floor_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("floors.id", ondelete="SET NULL"))
    suggested_floor_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    assignment_status: Mapped[str] = mapped_column(String(20), default="unassigned")
    calibration: Mapped[dict | None] = mapped_column(JSONB)
    calibration_status: Mapped[str] = mapped_column(String(20), default="none")
    hints: Mapped[dict] = mapped_column(JSONB, default=dict)
    version: Mapped[int] = mapped_column(default=1)


class Unit(TimestampMixin, Base):
    __tablename__ = "units"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_id)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), index=True
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    building_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("buildings.id", ondelete="RESTRICT"), index=True
    )
    floor_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("floors.id", ondelete="RESTRICT"), index=True
    )
    code: Mapped[str] = mapped_column(String(40))
    unit_type: Mapped[str] = mapped_column(String(20), default="apartment")
    lifecycle_status: Mapped[str] = mapped_column(String(20), default="draft")
    verification_status: Mapped[str] = mapped_column(String(20), default="unverified")
    publication_status: Mapped[str] = mapped_column(String(20), default="unpublished")
    created_from_revision_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    removed_by_revision_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    rooms: Mapped[int | None] = mapped_column()
    bedrooms: Mapped[int | None] = mapped_column()
    bathrooms: Mapped[int | None] = mapped_column()
    orientation: Mapped[str | None] = mapped_column(String(20))
    attributes: Mapped[dict] = mapped_column(JSONB, default=dict)
    version: Mapped[int] = mapped_column(default=1)


class UnitCodeHistory(Base):
    __tablename__ = "unit_code_history"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_id)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), index=True
    )
    unit_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("units.id", ondelete="CASCADE"), index=True
    )
    old_code: Mapped[str | None] = mapped_column(String(40))
    new_code: Mapped[str] = mapped_column(String(40))
    changed_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    revision_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    reason: Mapped[str | None] = mapped_column(Text)
    changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class UnitBoundary(TimestampMixin, Base):
    __tablename__ = "unit_boundaries"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_id)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), index=True
    )
    unit_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("units.id", ondelete="CASCADE"), index=True
    )
    sheet_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("sheets.id", ondelete="CASCADE"), index=True
    )
    polygon: Mapped[dict] = mapped_column(JSONB)  # normalised sheet coords: {"ring": [[x,y],...]}
    polygon_m: Mapped[dict | None] = mapped_column(JSONB)  # metres, after calibration
    source: Mapped[str] = mapped_column(String(20), default="manual")
    status: Mapped[str] = mapped_column(
        String(20), default="draft"
    )  # draft | approved | superseded
    is_current: Mapped[bool] = mapped_column(Boolean, default=True)
    label: Mapped[str | None] = mapped_column(String(80))
    approved_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    version: Mapped[int] = mapped_column(default=1)


class UnitLineageEvent(Base):
    __tablename__ = "unit_lineage_events"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_id)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), index=True
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    event_type: Mapped[str] = mapped_column(String(30))
    revision_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    from_unit_ids: Mapped[list[uuid.UUID]] = mapped_column(ARRAY(UUID(as_uuid=True)), default=list)
    to_unit_ids: Mapped[list[uuid.UUID]] = mapped_column(ARRAY(UUID(as_uuid=True)), default=list)
    decided_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    decided_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    note: Mapped[str | None] = mapped_column(Text)


class UnitArea(TimestampMixin, Base):
    __tablename__ = "unit_areas"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_id)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), index=True
    )
    unit_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("units.id", ondelete="CASCADE"), index=True
    )
    area_type: Mapped[str] = mapped_column(String(40))
    value_m2: Mapped[float] = mapped_column(Numeric(10, 2))
    source: Mapped[str] = mapped_column(
        String(20)
    )  # drawing_measured | drawing_schedule | ifc | manual
    source_ref: Mapped[dict | None] = mapped_column(JSONB)
    verification_status: Mapped[str] = mapped_column(String(20), default="unverified")
    verified_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_current: Mapped[bool] = mapped_column(Boolean, default=True)


# --- revision diff proposals (plan §5.5, §13.3) -----------------------------------------
class MappingProposal(TimestampMixin, Base):
    """Worker-produced diff between the current mapping and a new document revision.

    A proposal never touches ``units``; the reviewer accepts or rejects each item and the
    accepted ones are applied through the inventory service (identity-preserving operations).
    """

    __tablename__ = "mapping_proposals"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_id)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), index=True
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), index=True
    )
    old_revision_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    new_revision_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("document_revisions.id", ondelete="CASCADE"), index=True
    )
    status: Mapped[str] = mapped_column(String(20), default="open")  # open|resolved|dismissed
    summary: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class MappingProposalItem(TimestampMixin, Base):
    __tablename__ = "mapping_proposal_items"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_id)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), index=True
    )
    proposal_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("mapping_proposals.id", ondelete="CASCADE"), index=True
    )
    # matched | relabelled | split | merged | new | missing | complex
    kind: Mapped[str] = mapped_column(String(20))
    old_unit_ids: Mapped[list[uuid.UUID]] = mapped_column(ARRAY(UUID(as_uuid=True)), default=list)
    old_boundary_ids: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(UUID(as_uuid=True)), default=list
    )
    old_sheet_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    new_sheet_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("sheets.id", ondelete="SET NULL")
    )
    new_rings: Mapped[list] = mapped_column(JSONB, default=list)  # rings on the new sheet
    labels: Mapped[list] = mapped_column(JSONB, default=list)  # label per new ring (or None)
    overlaps: Mapped[list] = mapped_column(JSONB, default=list)  # [old_unit_id, ring_idx, ratio]
    confidence: Mapped[float] = mapped_column(Numeric(4, 3), default=0)
    decision: Mapped[str] = mapped_column(
        String(20), default="pending"
    )  # pending|accepted|rejected
    decided_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    result: Mapped[dict] = mapped_column(JSONB, default=dict)


# --- 3D geometry (plan §5.3 geometry_models, §11.3) -------------------------------------
class GeometryModel(TimestampMixin, Base):
    __tablename__ = "geometry_models"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_id)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), index=True
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    building_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("buildings.id", ondelete="SET NULL")
    )
    kind: Mapped[str] = mapped_column(String(30))  # massing_generated | glb_source | ifc
    revision_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    glb_key: Mapped[str | None] = mapped_column(String(512))
    model_transform: Mapped[dict] = mapped_column(JSONB, default=dict)
    units_scale: Mapped[float] = mapped_column(Numeric(10, 6), default=1)
    status: Mapped[str] = mapped_column(String(20), default="generating")  # generating|ready|failed
    stats: Mapped[dict] = mapped_column(JSONB, default=dict)
    error: Mapped[str | None] = mapped_column(Text)
    is_current: Mapped[bool] = mapped_column(Boolean, default=True)
