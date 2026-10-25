"""Sales service: inventory rows, the change engine, bulk edit, plans, promotions (plan §6).

Every write goes through :func:`apply_changes`, which validates, records price and
availability history, writes one audit entry per changed field and bumps the row version.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from unitforma.audit.service import write_audit
from unitforma.core.errors import ProblemError
from unitforma.core.ids import new_id
from unitforma.sales import rules
from unitforma.tenants.models import (
    AuditLog,
    AvailabilityHistory,
    Building,
    Floor,
    PaymentPlan,
    PriceHistory,
    Project,
    Promotion,
    Unit,
    UnitArea,
    UnitMedia,
    UnitSales,
)

Actor = tuple[uuid.UUID, str]


# --- reference data ---------------------------------------------------------------------------
async def load_lookups(db: AsyncSession, project: Project) -> rules.Lookups:
    plans = list(
        (
            await db.execute(select(PaymentPlan).where(PaymentPlan.project_id == project.id))
        ).scalars()
    )
    promos = list(
        (await db.execute(select(Promotion).where(Promotion.project_id == project.id))).scalars()
    )
    return rules.Lookups(
        area_keys={a.get("key") for a in (project.area_definitions or []) if isinstance(a, dict)},
        plan_ids={p.id for p in plans},
        plan_by_name={p.name.strip().lower(): p.id for p in plans},
        plan_names={p.id: p.name for p in plans},
        promotion_ids={p.id for p in promos},
        promotion_by_name={p.name.strip().lower(): p.id for p in promos},
        promotion_names={p.id: p.name for p in promos},
    )


# --- inventory rows ---------------------------------------------------------------------------
async def inventory(
    db: AsyncSession,
    project: Project,
    *,
    include_removed: bool = False,
    unit_ids: list[uuid.UUID] | None = None,
) -> list[dict[str, Any]]:
    q = (
        select(Unit, Building, Floor, UnitSales)
        .join(Building, Building.id == Unit.building_id)
        .join(Floor, Floor.id == Unit.floor_id)
        .outerjoin(UnitSales, UnitSales.unit_id == Unit.id)
        .where(Unit.project_id == project.id)
    )
    if not include_removed:
        q = q.where(Unit.lifecycle_status != "removed")
    if unit_ids is not None:
        q = q.where(Unit.id.in_(unit_ids))
    rows = list(
        await db.execute(q.order_by(Building.sort_order, Building.code, Floor.level, Unit.code))
    )
    areas_q = (
        select(UnitArea)
        .join(Unit, Unit.id == UnitArea.unit_id)
        .where(Unit.project_id == project.id, UnitArea.is_current.is_(True))
    )
    if unit_ids is not None:
        areas_q = areas_q.where(UnitArea.unit_id.in_(unit_ids))
    areas: dict[uuid.UUID, list[UnitArea]] = {}
    for a in (await db.execute(areas_q)).scalars():
        areas.setdefault(a.unit_id, []).append(a)
    media_counts = dict(
        (
            await db.execute(
                select(UnitMedia.unit_id, func.count())
                .where(UnitMedia.project_id == project.id, UnitMedia.status == "ready")
                .group_by(UnitMedia.unit_id)
            )
        ).all()
    )
    lookups = await load_lookups(db, project)
    return [
        row_dict(project, u, b, f, s, areas.get(u.id, []), media_counts.get(u.id, 0), lookups)
        for u, b, f, s in rows
    ]


def row_dict(project, unit, building, floor, sales, areas, media_count, lookups) -> dict[str, Any]:
    cur = rules.current_values(project, unit, sales).values
    pat = rules.resolve_price_area_type(project, sales)
    area = rules.best_area(areas, pat)
    by_type: dict[str, Decimal] = {}
    for t in {a.area_type for a in areas}:
        best = rules.best_area(areas, t)
        if best is not None:
            by_type[t] = Decimal(best.value_m2)
    return {
        "unit_id": unit.id,
        "code": unit.code,
        "building_id": building.id,
        "building_code": building.code,
        "floor_id": floor.id,
        "floor_level": floor.level,
        "floor_name": floor.display_name,
        "unit_type": unit.unit_type,
        "lifecycle_status": unit.lifecycle_status,
        "verification_status": unit.verification_status,
        "publication_status": unit.publication_status,
        "availability": cur["availability"],
        "availability_reason": cur["availability_reason"],
        "availability_changed_at": sales.availability_changed_at if sales else None,
        "list_price": cur["list_price"],
        "currency": cur["currency"],
        "price_on_request": cur["price_on_request"],
        "price_area_type": pat,
        "price_area_type_override": cur["price_area_type"],
        "price_area_m2": Decimal(area.value_m2) if area is not None else None,
        "price_area_source": area.source if area is not None else None,
        "price_area_verified": area is not None and area.verification_status == "verified",
        "price_per_m2": rules.price_per_area(cur["list_price"], area),
        "payment_plan_id": cur["payment_plan_id"],
        "payment_plan_name": lookups.plan_names.get(cur["payment_plan_id"]),
        "promotion_ids": cur["promotion_ids"],
        "promotion_names": [
            lookups.promotion_names[p] for p in cur["promotion_ids"] if p in lookups.promotion_names
        ],
        "rooms": unit.rooms,
        "bedrooms": unit.bedrooms,
        "bathrooms": unit.bathrooms,
        "orientation": unit.orientation,
        "entrance": unit.entrance,
        "layout": (unit.attributes or {}).get("layout"),
        "public_description": cur["public_description"],
        "internal_notes": cur["internal_notes"],
        "public_fields": rules.effective_public_fields(project, sales),
        "public_field_overrides": cur["public_fields"],
        "areas": by_type,
        "media_count": media_count,
        "version": sales.version if sales else 0,
        "updated_at": sales.updated_at if sales else None,
    }


async def get_unit_in_project(db: AsyncSession, tenant_id: uuid.UUID, unit_id: uuid.UUID) -> Unit:
    u = (
        await db.execute(select(Unit).where(Unit.tenant_id == tenant_id, Unit.id == unit_id))
    ).scalar_one_or_none()
    if u is None:
        raise ProblemError(404, "Unit not found")
    return u


async def get_sales(db: AsyncSession, unit_id: uuid.UUID, lock: bool = False) -> UnitSales | None:
    q = select(UnitSales).where(UnitSales.unit_id == unit_id)
    if lock:
        q = q.with_for_update()
    return (await db.execute(q)).scalar_one_or_none()


async def unit_row(db: AsyncSession, project: Project, unit_id: uuid.UUID) -> dict[str, Any]:
    rows = await inventory(db, project, include_removed=True, unit_ids=[unit_id])
    if not rows:
        raise ProblemError(404, "Unit not found")
    return rows[0]


# --- the change engine --------------------------------------------------------------------------
async def apply_changes(
    db: AsyncSession,
    *,
    project: Project,
    unit: Unit,
    sales: UnitSales | None,
    diffs: list[rules.FieldDiff],
    actor: Actor,
    reason: str | None = None,
    import_batch_id: uuid.UUID | None = None,
) -> UnitSales | None:
    """Write already-validated diffs. Creates the sales row on first write."""
    if not diffs:
        return sales
    if unit.lifecycle_status == "removed":
        raise ProblemError(409, f"Unit {unit.code} is removed and cannot be edited")
    now = datetime.now(UTC)
    if sales is None:
        sales = UnitSales(
            unit_id=unit.id,
            tenant_id=unit.tenant_id,
            project_id=unit.project_id,
            availability="available",
            currency=project.currency,
            price_on_request=False,
            promotion_ids=[],
            public_fields={},
            version=0,
        )
        db.add(sales)
    old = {d.field: d.old for d in diffs}
    new = {d.field: d.new for d in diffs}
    unit_changed = False
    for d in diffs:
        if d.field in rules.ATTRIBUTE_FIELDS:
            attrs = dict(unit.attributes or {})
            if d.new is None:
                attrs.pop(d.field, None)
            else:
                attrs[d.field] = d.new
            unit.attributes = attrs
            unit_changed = True
        elif d.field in rules.UNIT_FIELDS:
            setattr(unit, d.field, d.new)
            unit_changed = True
        else:
            setattr(sales, d.field, d.new)
    if unit_changed:
        unit.version += 1
    if "availability" in new:
        sales.availability_changed_at = now
        if "availability_reason" not in new:
            sales.availability_reason = reason
        db.add(
            AvailabilityHistory(
                id=new_id(),
                tenant_id=unit.tenant_id,
                unit_id=unit.id,
                old_availability=old["availability"],
                new_availability=new["availability"],
                changed_by=actor[0],
                reason=new.get("availability_reason") or reason,
                import_batch_id=import_batch_id,
            )
        )
    if "list_price" in new or "currency" in new:
        db.add(
            PriceHistory(
                id=new_id(),
                tenant_id=unit.tenant_id,
                unit_id=unit.id,
                old_price=old.get("list_price", sales.list_price),
                new_price=sales.list_price,
                old_currency=old.get("currency", sales.currency),
                new_currency=sales.currency,
                changed_by=actor[0],
                reason=reason,
                import_batch_id=import_batch_id,
            )
        )
    sales.updated_by = actor[0]
    sales.version += 1
    sales.updated_at = now
    for d in diffs:  # one audit entry per changed field (plan §6.3)
        after = {d.field: rules.to_json(d.new), "code": unit.code}
        if import_batch_id:
            after["import_batch_id"] = str(import_batch_id)
        if reason:
            after["reason"] = reason
        await write_audit(
            db,
            tenant_id=unit.tenant_id,
            actor_user_id=actor[0],
            actor_role=actor[1],
            entity_type="unit" if d.field in rules.UNIT_FIELDS else "unit_sales",
            entity_id=unit.id,
            action="import" if import_batch_id else "update",
            before={d.field: rules.to_json(d.old)},
            after=after,
        )
    await db.flush()
    return sales


def conflict(row: dict[str, Any], sent: int) -> ProblemError:
    return ProblemError(
        409,
        "Conflict",
        f"The unit changed since you loaded it (current version {row['version']}, "
        f"you sent {sent}). Review the current values and re-apply your edit.",
        extra={"current": rules.to_json(row)},  # decimals as strings, like a GET
    )


async def update_unit_sales(
    db: AsyncSession,
    project: Project,
    unit: Unit,
    changes: dict[str, Any],
    *,
    version: int,
    actor: Actor,
    reason: str | None,
    confirm_zero_price: bool,
) -> dict[str, Any]:
    sales = await get_sales(db, unit.id, lock=True)
    cur = rules.current_values(project, unit, sales)
    if cur.version != version:
        raise conflict(await unit_row(db, project, unit.id), version)
    if "currency" in changes and isinstance(changes["currency"], str):
        changes["currency"] = changes["currency"].strip().upper()
    diffs = rules.diff(cur, changes)
    lookups = await load_lookups(db, project)
    errors = rules.validate(diffs, cur, lookups, allow_zero_price=confirm_zero_price, reason=reason)
    if errors:
        raise ProblemError(422, "Invalid sales data", "; ".join(errors))
    await apply_changes(
        db, project=project, unit=unit, sales=sales, diffs=diffs, actor=actor, reason=reason
    )
    return await unit_row(db, project, unit.id)


async def bulk_update(
    db: AsyncSession,
    project: Project,
    items: list[tuple[uuid.UUID, int]],
    changes: dict[str, Any],
    *,
    price_adjust_percent: Decimal | None,
    preview: bool,
    actor: Actor,
    reason: str | None,
    confirm_zero_price: bool,
) -> dict[str, Any]:
    """Set the same values on N units in one transaction, all-or-nothing (plan §6.3, §6.4)."""
    if not items:
        raise ProblemError(422, "Select at least one unit")
    if len({i for i, _ in items}) != len(items):
        raise ProblemError(422, "A unit is listed twice")
    if "currency" in changes and isinstance(changes["currency"], str):
        changes["currency"] = changes["currency"].strip().upper()
    lookups = await load_lookups(db, project)
    units = {
        u.id: u
        for u in (
            await db.execute(
                select(Unit).where(
                    Unit.project_id == project.id, Unit.id.in_([i for i, _ in items])
                )
            )
        ).scalars()
    }
    stale: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    plan: list[tuple[Unit, UnitSales | None, list[rules.FieldDiff]]] = []
    for unit_id, version in items:
        unit = units.get(unit_id)
        if unit is None:
            errors.append({"unit_id": str(unit_id), "errors": ["unit not in this project"]})
            continue
        if unit.lifecycle_status == "removed":
            errors.append(
                {"unit_id": str(unit_id), "code": unit.code, "errors": ["unit is removed"]}
            )
            continue
        sales = await get_sales(db, unit_id, lock=not preview)
        cur = rules.current_values(project, unit, sales)
        if cur.version != version:
            stale.append({"unit_id": str(unit_id), "code": unit.code, "version": cur.version})
            continue
        unit_changes = dict(changes)
        if price_adjust_percent is not None and cur.values["list_price"] is not None:
            factor = Decimal(1) + Decimal(price_adjust_percent) / Decimal(100)
            unit_changes["list_price"] = (cur.values["list_price"] * factor).quantize(
                Decimal("0.01")
            )
        diffs = rules.diff(cur, unit_changes)
        errs = rules.validate(
            diffs, cur, lookups, allow_zero_price=confirm_zero_price, reason=reason
        )
        if errs:
            errors.append({"unit_id": str(unit_id), "code": unit.code, "errors": errs})
        plan.append((unit, sales, diffs))
    if stale:
        raise ProblemError(
            409,
            "Conflict",
            f"{len(stale)} unit(s) changed since you loaded them; reload and re-apply",
            extra={"stale": stale},
        )
    if errors:
        raise ProblemError(
            422, "Invalid bulk edit", "Nothing was changed", extra={"unit_errors": errors}
        )
    result = [
        {
            "unit_id": str(u.id),
            "code": u.code,
            "changes": [d.as_json() for d in diffs],
        }
        for u, _s, diffs in plan
    ]
    changed = sum(1 for _u, _s, d in plan if d)
    if not preview:
        for unit, sales, diffs in plan:
            await apply_changes(
                db,
                project=project,
                unit=unit,
                sales=sales,
                diffs=diffs,
                actor=actor,
                reason=reason,
            )
    return {"preview": preview, "units": result, "changed_units": changed}


# --- project sales settings -----------------------------------------------------------------
async def update_settings(
    db: AsyncSession, project: Project, settings: dict[str, Any], version: int, actor: Actor
) -> Project:
    if project.version != version:
        raise ProblemError(409, "Conflict", f"Project changed (current version {project.version})")
    lookups = await load_lookups(db, project)
    pat = settings.get("price_area_type")
    if pat is not None and pat not in lookups.area_keys:
        raise ProblemError(422, f"Area type '{pat}' is not defined for this project")
    pf = settings.get("public_fields") or {}
    if any(k not in rules.PUBLIC_FIELD_KEYS or not isinstance(v, bool) for k, v in pf.items()):
        raise ProblemError(422, "public_fields accepts only known keys with boolean values")
    before = dict(project.sales_settings or {})
    merged = {**before, **{k: v for k, v in settings.items() if v is not None}}
    project.sales_settings = merged
    project.version += 1
    await write_audit(
        db,
        tenant_id=project.tenant_id,
        actor_user_id=actor[0],
        actor_role=actor[1],
        entity_type="project",
        entity_id=project.id,
        action="sales_settings",
        before=rules.to_json(before),
        after=rules.to_json(merged),
    )
    return project


# --- payment plans & promotions ----------------------------------------------------------------
def validate_schedule(schedule: list[dict[str, Any]]) -> None:
    if not schedule:
        return
    total = sum(Decimal(str(m.get("percent", 0))) for m in schedule)
    if total != Decimal(100):
        raise ProblemError(
            422, "Payment plan milestones must add up to 100 %", f"they add up to {total}"
        )


async def create_plan(db, project: Project, data: dict[str, Any], actor: Actor) -> PaymentPlan:
    validate_schedule(data.get("schedule") or [])
    await _unique_name(db, PaymentPlan, project.id, data["name"])
    p = PaymentPlan(id=new_id(), tenant_id=project.tenant_id, project_id=project.id, **data)
    db.add(p)
    await db.flush()
    await _audit(db, actor, project.tenant_id, "payment_plan", p.id, "create", None, data)
    return p


async def update_plan(db, plan: PaymentPlan, data: dict[str, Any], version: int, actor: Actor):
    if plan.version != version:
        raise ProblemError(
            409, "Conflict", f"Payment plan changed (current version {plan.version})"
        )
    if "schedule" in data:
        validate_schedule(data["schedule"] or [])
    if "name" in data and data["name"].strip().lower() != plan.name.strip().lower():
        await _unique_name(db, PaymentPlan, plan.project_id, data["name"])
    before = {k: getattr(plan, k) for k in data}
    for k, v in data.items():
        setattr(plan, k, v)
    plan.version += 1
    await _audit(db, actor, plan.tenant_id, "payment_plan", plan.id, "update", before, data)
    return plan


async def create_promotion(db, project: Project, data: dict[str, Any], actor: Actor) -> Promotion:
    _check_dates(data)
    await _unique_name(db, Promotion, project.id, data["name"])
    p = Promotion(id=new_id(), tenant_id=project.tenant_id, project_id=project.id, **data)
    db.add(p)
    await db.flush()
    await _audit(db, actor, project.tenant_id, "promotion", p.id, "create", None, data)
    return p


async def update_promotion(db, promo: Promotion, data: dict[str, Any], version: int, actor: Actor):
    if promo.version != version:
        raise ProblemError(409, "Conflict", f"Promotion changed (current version {promo.version})")
    merged = {
        "valid_from": data.get("valid_from", promo.valid_from),
        "valid_to": data.get("valid_to", promo.valid_to),
    }
    _check_dates(merged)
    if "name" in data and data["name"].strip().lower() != promo.name.strip().lower():
        await _unique_name(db, Promotion, promo.project_id, data["name"])
    before = {k: getattr(promo, k) for k in data}
    for k, v in data.items():
        setattr(promo, k, v)
    promo.version += 1
    await _audit(db, actor, promo.tenant_id, "promotion", promo.id, "update", before, data)
    return promo


def _check_dates(d: dict[str, Any]) -> None:
    if d.get("valid_from") and d.get("valid_to") and d["valid_to"] < d["valid_from"]:
        raise ProblemError(422, "valid_to is before valid_from")


async def _unique_name(db, model, project_id: uuid.UUID, name: str) -> None:
    exists = (
        await db.execute(
            select(model.id).where(
                model.project_id == project_id, func.lower(model.name) == name.strip().lower()
            )
        )
    ).first()
    if exists:
        raise ProblemError(409, f"'{name}' already exists in this project")


async def _audit(db, actor, tenant_id, entity_type, entity_id, action, before, after) -> None:
    await write_audit(
        db,
        tenant_id=tenant_id,
        actor_user_id=actor[0],
        actor_role=actor[1],
        entity_type=entity_type,
        entity_id=entity_id,
        action=action,
        before=rules.to_json(before) if before else None,
        after=rules.to_json(after) if after else None,
    )


# --- history & public view ---------------------------------------------------------------------
async def history(db: AsyncSession, unit_id: uuid.UUID) -> dict[str, Any]:
    prices = (
        await db.execute(
            select(PriceHistory)
            .where(PriceHistory.unit_id == unit_id)
            .order_by(PriceHistory.changed_at.desc())
        )
    ).scalars()
    avail = (
        await db.execute(
            select(AvailabilityHistory)
            .where(AvailabilityHistory.unit_id == unit_id)
            .order_by(AvailabilityHistory.changed_at.desc())
        )
    ).scalars()
    audit = (
        await db.execute(
            select(AuditLog)
            .where(
                AuditLog.entity_id == unit_id,
                AuditLog.entity_type.in_(("unit_sales", "unit", "unit_media")),
            )
            .order_by(AuditLog.at.desc())
            .limit(500)
        )
    ).scalars()
    return {"prices": list(prices), "availability": list(avail), "audit": list(audit)}


def public_view(
    row: dict[str, Any], plan: PaymentPlan | None, promos: list[Promotion], media: list[UnitMedia]
) -> dict[str, Any]:
    """The only shape of sales data that may leave the workspace (plan §6.6).

    Built from an allow-list: fields are copied in, never filtered out, so a new internal
    column cannot leak by default. The Phase 4 snapshot builder uses this function.
    """
    pf = row["public_fields"]
    out: dict[str, Any] = {
        "unit_id": row["unit_id"],
        "code": row["code"],
        "building_code": row["building_code"],
        "floor_level": row["floor_level"],
        "unit_type": row["unit_type"],
        "availability": row["availability"],
        "indicative": row["verification_status"] != "verified",
    }
    if row.get("entrance"):
        out["entrance"] = row["entrance"]  # a location fact like the floor: public, no switch
    if row.get("layout"):
        out["layout"] = row["layout"]  # the plan type; renders of the same layout are shared
    if pf.get("list_price") and row["list_price"] is not None and not row["price_on_request"]:
        out["price"] = {"amount": row["list_price"], "currency": row["currency"]}
        if row["price_per_m2"] is not None:
            out["price"]["per_m2"] = row["price_per_m2"]
            out["price"]["per_m2_area_type"] = row["price_area_type"]
            out["price"]["per_m2_area_verified"] = row["price_area_verified"]
    else:
        out["price"] = None  # "price on request"
    if pf.get("areas"):
        out["areas"] = row["areas"]
    if pf.get("rooms"):
        out["rooms"] = {k: row[k] for k in ("rooms", "bedrooms", "bathrooms", "orientation")}
    if pf.get("description") and row["public_description"]:
        out["description"] = row["public_description"]
    if pf.get("payment_plan") and plan is not None and plan.is_public and plan.is_active:
        out["payment_plan"] = {
            "name": plan.name,
            "description": plan.description,
            "schedule": plan.schedule,
        }
    if pf.get("promotions"):
        out["promotions"] = [
            {
                "name": p.name,
                "kind": p.kind,
                "value": p.value,
                "terms": p.terms,
                "valid_from": p.valid_from,
                "valid_to": p.valid_to,
            }
            for p in promos
            if p.is_public and p.is_active
        ]
    if pf.get("media"):
        out["media"] = [
            {
                "id": m.id,
                "kind": m.kind,
                "alt_text": m.alt_text,
                "is_ai_generated": m.is_ai_generated,
                "ai_disclosure_text": m.ai_disclosure_text,
            }
            for m in media
            if m.is_public and m.status == "ready"
        ]
    return rules.to_json(out)
