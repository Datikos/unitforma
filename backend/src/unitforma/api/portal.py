"""Public portal API (plan §12.2): anonymous, tenant resolved from the Host header.

Every response is built from a publication snapshot or the published read model, never from
live inventory tables. Live responses may be cached briefly (5 s) so an unpublish takes
effect within seconds; preview responses are never cached.
"""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Header, Query, Request, Response
from fastapi.responses import RedirectResponse

from unitforma.core.db import tenant_session
from unitforma.core.errors import ProblemError
from unitforma.domains.service import normalise_hostname
from unitforma.publishing import portal
from unitforma.storage.service import get_storage

router = APIRouter(prefix="/api/v1/portal", tags=["portal"])

Preview = Annotated[str | None, Query(max_length=512, description="Signed preview token")]
PreviewHeader = Annotated[str | None, Header(alias="X-Unitforma-Preview", max_length=512)]


def _host(request: Request) -> str:
    return normalise_hostname(
        request.headers.get("x-forwarded-host") or request.headers.get("host", "")
    )


def _cache(response: Response, preview: bool) -> None:
    response.headers["Cache-Control"] = "no-store" if preview else "public, max-age=5"
    response.headers["Vary"] = "Host, X-Forwarded-Host"


@router.get("/site", response_model=dict)
async def site(request: Request, response: Response):
    """Landing data for this host: branding, mode (tenant portal or single project) and the
    live projects. ``status`` is ``coming_soon`` when nothing is published."""
    s = await portal.site_for_host(_host(request))
    _cache(response, False)
    return await portal.site_summary(s)


@router.get("/branding", response_model=dict)
async def branding(request: Request, response: Response):
    s = await portal.site_for_host(_host(request))
    out = await portal.site_summary(s)
    _cache(response, False)
    return {"tenant": out["tenant"], "branding": out["branding"], "mode": out["mode"]}


@router.get("/projects/{slug}", response_model=dict)
async def project(
    slug: str,
    request: Request,
    response: Response,
    preview: Preview = None,
    xp: PreviewHeader = None,
):
    """The project snapshot: project text, site, buildings → floors → unit polygons, massing."""
    s = await portal.site_for_host(_host(request))
    async with tenant_session(s.tenant_id) as db:
        _p, pub, is_preview = await portal.resolve_publication(db, s, slug, preview or xp)
        doc = portal.load_doc(pub)
    _cache(response, is_preview)
    return {**doc, "preview": is_preview}


@router.get("/projects/{slug}/units", response_model=dict)
async def units(
    slug: str,
    request: Request,
    response: Response,
    availability: Annotated[
        list[Literal["available", "reserved", "sold", "withdrawn"]] | None, Query()
    ] = None,
    unit_type: Annotated[list[str] | None, Query(max_length=10)] = None,
    building: Annotated[list[str] | None, Query(max_length=50)] = None,
    floor: Annotated[list[int] | None, Query(max_length=200)] = None,
    rooms: Annotated[list[int] | None, Query(max_length=10, description="5 = five or more")] = None,
    min_price: Annotated[float | None, Query(ge=0)] = None,
    max_price: Annotated[float | None, Query(ge=0)] = None,
    min_area: Annotated[float | None, Query(ge=0)] = None,
    max_area: Annotated[float | None, Query(ge=0)] = None,
    sort: Literal["code", "price_asc", "price_desc", "area_asc", "area_desc"] = "code",
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=500)] = 200,
    preview: Preview = None,
    xp: PreviewHeader = None,
):
    """Listed units with filters (published read model). A price filter excludes units
    whose price is on request."""
    s = await portal.site_for_host(_host(request))
    async with tenant_session(s.tenant_id) as db:
        _p, pub, is_preview = await portal.resolve_publication(db, s, slug, preview or xp)
        out = await portal.list_units(
            db,
            pub,
            {
                "availability": availability,
                "unit_type": unit_type,
                "building": [b.upper() for b in building] if building else None,
                "floor": floor,
                "rooms": rooms,
                "min_price": min_price,
                "max_price": max_price,
                "min_area": min_area,
                "max_area": max_area,
                "sort": sort,
                "offset": offset,
                "limit": limit,
            },
        )
    _cache(response, is_preview)
    return out


@router.get("/projects/{slug}/units/{code}", response_model=dict)
async def unit(
    slug: str,
    code: str,
    request: Request,
    response: Response,
    preview: Preview = None,
    xp: PreviewHeader = None,
):
    """One unit (listed or hidden-but-linkable) as published."""
    s = await portal.site_for_host(_host(request))
    async with tenant_session(s.tenant_id) as db:
        _p, pub, is_preview = await portal.resolve_publication(db, s, slug, preview or xp)
        data = await portal.get_unit(db, pub, code)
    _cache(response, is_preview)
    return data


@router.get("/projects/{slug}/assets/{name}", include_in_schema=True)
async def asset(
    slug: str, name: str, request: Request, preview: Preview = None, xp: PreviewHeader = None
):
    """Redirect to a short-lived signed URL of a published asset. Only names listed in the
    publication being served resolve, so internal objects are unreachable by construction."""
    s = await portal.site_for_host(_host(request))
    async with tenant_session(s.tenant_id) as db:
        _p, pub, _ = await portal.resolve_publication(db, s, slug, preview or xp)
        key = (pub.assets or {}).get(name)
    if key is None:
        raise ProblemError(404, "Asset not found")
    resp = RedirectResponse(get_storage().presign_get(key, expires=3600), status_code=302)
    resp.headers["Cache-Control"] = "private, max-age=300"
    return resp
