"""Worker entry point for ``renders.generate`` (ADR-0017 Decision 3).

Three short steps so no database connection is held across the provider call (plan §12.3,
backlog #15): read the inputs and mark the row running; crop and call the provider with no
session open; store the result or the error.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import structlog
from sqlalchemy import select

from unitforma.core.db import tenant_session
from unitforma.renders import service
from unitforma.renders.provider import ProviderError, get_provider
from unitforma.storage.service import get_storage, object_key
from unitforma.tenants.models import Unit, UnitRender

log = structlog.get_logger()


async def generate(tenant_id: uuid.UUID, render_id: uuid.UUID) -> dict:
    # 1. inputs
    async with tenant_session(tenant_id, scope="tenant") as db:
        r = (await db.execute(select(UnitRender).where(UnitRender.id == render_id))).scalar_one()
        if r.status not in service.ACTIVE:
            return {"status": r.status}
        unit = (await db.execute(select(Unit).where(Unit.id == r.unit_id))).scalar_one()
        outline = await service.current_outline(db, unit.id)
        r.status = "running"
        r.started_at = datetime.now(UTC)
        if outline is None or not outline[1].raster_key:
            r.status = "failed"
            r.error = "the unit has no outline on a processed sheet"
            r.finished_at = datetime.now(UTC)
            return {"status": r.status}
        boundary, sheet = outline
        ring = list((boundary.polygon or {}).get("ring") or [])
        extra: list[list[list[float]]] = []
        partner_code: str | None = None
        if r.partner_unit_id is not None:
            partner = (
                await db.execute(select(Unit).where(Unit.id == r.partner_unit_id))
            ).scalar_one_or_none()
            p_outline = await service.current_outline(db, r.partner_unit_id)
            if partner is not None and p_outline is not None:
                extra.append(list((p_outline[0].polygon or {}).get("ring") or []))
                partner_code = partner.code
        raster_key = sheet.raster_key
        prompt = r.prompt
        input_key = object_key(
            unit.tenant_id, unit.project_id, "renders", str(unit.id), f"{r.id.hex[:12]}-plan.png"
        )
    # 2. no session open: crop, store the crop, call the provider
    image = None
    error: str | None = None
    try:
        crop = service.crop_plan(get_storage().get_bytes(raster_key), ring, extra_rings=extra)
        get_storage().put_bytes(input_key, crop, "image/png")
        provider = get_provider()
        if provider is None:
            raise ProviderError("UF_AI_IMAGE_PROVIDER is none")
        image = await provider.edit(crop, "image/png", prompt)
    except (ProviderError, ValueError, OSError) as e:
        error = str(e)[:1000]
    # 3. result
    async with tenant_session(tenant_id, scope="tenant") as db:
        r = (await db.execute(select(UnitRender).where(UnitRender.id == render_id))).scalar_one()
        unit = (await db.execute(select(Unit).where(Unit.id == r.unit_id))).scalar_one()
        r.input_key = input_key
        if error is not None or image is None:
            r.status = "failed"
            r.error = error or "no image"
            r.finished_at = datetime.now(UTC)
            log.warning("renders.failed", render_id=str(render_id), error=r.error[:200])
            return {"status": r.status, "error": r.error}
        m = await service.store_result(db, r, unit, image, partner_code)
        log.info(
            "renders.generated",
            render_id=str(render_id),
            media_id=str(m.id),
            bytes=len(image.data),
            cost_usd=image.cost_usd,
        )
        return {"status": r.status, "media_id": str(m.id)}
