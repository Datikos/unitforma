"""ADR-0030 #D2: each floor sheet is registered to its building on the drawing's grid axes.

The axis rules (pure): two bubbles of a label make an axis, an ambiguous label and a bubble far
from the outlines do not count, the shift is the median over the shared axes and too few or
disagreeing axes leave the floor as drawn. On the publishing world: the solver pass writes the
shift on ``sheet_floors``, the massing and the footprint read the outlines moved by it, a second
run changes nothing and queues nothing."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace as NS
from typing import Any

import pytest

from tests import test_phase4_publishing as phase4
from tests.test_phase4_publishing import (
    _admin_sql,
    world,  # noqa: F401 - module-scoped fixture, rebuilt here
)
from tests.test_site_outline import _waiting_massing
from unitforma.geometry import registration as reg

LONG_AGO = datetime(2000, 1, 1, tzinfo=UTC)
W_M, H_M = 100.0, 70.0  # a sheet's size in metres in the pure tests
NEAR = (20.0, 20.0, 60.0, 40.0)  # the floor's outlines


def _bubble(label: str, x: float, y: float, w_m: float = W_M, h_m: float = H_M) -> dict[str, Any]:
    return {
        "t": label,
        "x0": (x - 0.2) / w_m,
        "x1": (x + 0.2) / w_m,
        "y0": (y - 0.2) / h_m,
        "y1": (y + 0.2) / h_m,
    }


def _grid_words(dx: float = 0.0, dy: float = 0.0, **size: float) -> list[dict[str, Any]]:
    """Axes 1-3 vertical at x 25/35/50 and A-B horizontal at y 25/35, bubbles 5 m outside the
    outlines, everything moved by (dx, dy) as another sheet origin would."""
    words = []
    for label, x in (("1", 25), ("2", 35), ("3", 50)):
        words += [_bubble(label, x + dx, 15 + dy, **size), _bubble(label, x + dx, 45 + dy, **size)]
    for label, y in (("A", 25), ("B", 35)):
        words += [_bubble(label, 15 + dx, y + dy, **size), _bubble(label, 65 + dx, y + dy, **size)]
    return words


def test_two_bubbles_of_a_label_make_an_axis():
    g = reg.grid_axes(_grid_words(), W_M, H_M, NEAR)
    assert g.vertical == pytest.approx({"1": 25, "2": 35, "3": 50})
    assert g.horizontal == pytest.approx({"A": 25, "B": 35})


def test_an_ambiguous_label_a_far_bubble_and_plain_words_are_not_axes():
    words = _grid_words()
    words += [_bubble("1", 30, 15), _bubble("1", 30, 45)]  # a second pair of "1"
    words += [_bubble("C", 15, 68), _bubble("C", 95, 68)]  # a title-block line, 28 m off
    words += [_bubble("ბინა", 25, 15), _bubble("ბინა", 25, 45), _bubble("ა", 40, 15)]
    g = reg.grid_axes(words, W_M, H_M, NEAR)
    assert set(g.vertical) == {"2", "3"} and set(g.horizontal) == {"A", "B"}
    assert reg.is_axis_label("ა") and reg.is_axis_label("12") and not reg.is_axis_label("x")


def test_the_shift_is_the_median_over_the_shared_axes():
    ref = reg.grid_axes(_grid_words(), W_M, H_M, NEAR)
    other = reg.grid_axes(_grid_words(2.0, -3.0), W_M, H_M, (22.0, 17.0, 62.0, 37.0))
    out = reg.register(ref, other)
    assert out["method"] == "grid_axes" and out["axes"] == [3, 2]
    assert (out["dx_m"], out["dy_m"]) == pytest.approx((-2.0, 3.0)) and out["spread_m"] < 0.01


def test_too_few_or_disagreeing_axes_leave_the_floor_as_drawn():
    ref = reg.grid_axes(_grid_words(), W_M, H_M, NEAR)
    one = reg.Grid(vertical={"1": 25, "2": 35}, horizontal={"A": 25})
    out = reg.register(ref, one)
    assert out["method"] == "none" and "1 horizontal" in out["reason"]
    # another scale: the axes 25 m apart come out 1 m further apart
    stretched = reg.Grid(vertical={"1": 25, "2": 35, "3": 51}, horizontal={"A": 25, "B": 35})
    out = reg.register(ref, stretched)
    assert out["method"] == "none" and "disagree by 1.00 m" in out["reason"]


def test_a_conversion_is_stale_where_a_floor_moved_since_it_ran():
    from unitforma.geometry.service import realigned

    now = {"s1:f1": [0.1, -2.3], "s2:f2": [0.0, 1.79]}
    # a conversion from before the alignment recorded nothing: every registered floor moved
    assert realigned({}, now) == {"s1:f1", "s2:f2"}
    assert realigned(now, now) == set()
    # centimetres of rounding are not a move; a floor whose registration was dropped is
    assert realigned({"s1:f1": [0.12, -2.28], "s2:f2": [0.0, 1.79]}, now) == set()
    assert realigned({"s1:f1": [0.1, -2.3], "s2:f2": [0.0, 1.79], "s3:f3": [1, 0]}, now) == {
        "s3:f3"
    }


# ------------------------------------------------------------------ the pass, on the world
def _sheet_floors(project_id: str) -> list[tuple[Any, ...]]:
    return _admin_sql(
        "SELECT f.level, sf.sheet_id, sf.registration, s.raster_width, s.raster_height,"
        " (s.calibration->>'m_per_px')::float FROM sheet_floors sf"
        " JOIN floors f ON f.id = sf.floor_id JOIN buildings b ON b.id = f.building_id"
        " JOIN sheets s ON s.id = sf.sheet_id WHERE b.project_id = :p ORDER BY f.level",
        {"p": project_id},
    )


@phase4.pytestmark
def test_the_pass_registers_a_floor_drawn_on_another_origin_and_readers_apply_it(
    client,
    world,  # noqa: F811
    monkeypatch,
):
    from unitforma.autopilot.passes import registration as reg_pass
    from unitforma.autopilot.service import Context
    from unitforma.core.db import tenant_session
    from unitforma.geometry import ifc_service
    from unitforma.geometry import service as geometry_service
    from unitforma.geometry.service import registration_used
    from unitforma.tenants.models import Project

    pid, tid = world["project"]["id"], world["tenant"]["id"]
    rows = _sheet_floors(pid)
    assert [r[0] for r in rows] == [0, 1] and all(r[2] is None for r in rows)
    # both pages draw the units at the same sheet metres (the world's PDF); level 1's sheet
    # prints its grid 2 m right and 3 m down, as a sheet with another origin would
    words = {}
    for level, sheet_id, _reg, w, h, m in rows:
        shift = (2.0, -3.0) if level == 1 else (0.0, 0.0)
        words[sheet_id] = _world_grid(pid, w * m, h * m, *shift)
    monkeypatch.setattr(reg_pass, "load_extract", lambda sheet: {"words": words[sheet.id]})

    def ctx() -> Context:
        actor = (uuid.uuid4(), "system")
        return Context(uuid.UUID(tid), uuid.UUID(pid), uuid.uuid4(), actor, False)

    assert _waiting_massing(pid, clear=True) == 0
    first = ctx()
    client.portal.call(reg_pass.run, first)
    by_level = {r[0]: r[2] for r in _sheet_floors(pid)}
    assert by_level[0]["method"] == "same_sheet"
    assert by_level[1]["method"] == "grid_axes" and by_level[1]["axes"] == [3, 2]
    assert (by_level[1]["dx_m"], by_level[1]["dy_m"]) == pytest.approx((-2.0, 3.0))
    [decision] = first.decisions
    assert decision["kind"] == "accepted" and "level 1 by 3.6 m" in decision["detail"]
    assert _waiting_massing(pid) == 1

    async def read() -> tuple[dict[int, list[Any]], list[Any], dict[int, list[Any]]]:
        async with tenant_session(uuid.UUID(tid), scope="tenant") as db:
            project = await db.get(Project, uuid.UUID(pid))
            solids, _stats = await geometry_service.collect(db, project)
            fps = await geometry_service.footprints(db, project)
            _floors, outlines = await ifc_service._plan_inputs(
                db, project.id, uuid.UUID(str(fps[0]["building_id"]))
            )
        rings: dict[int, list[Any]] = {}
        for u in solids[0].units:
            rings.setdefault(u.floor_level, []).append(u.ring_m)
        plan: dict[int, list[Any]] = {}
        for o in outlines:
            plan.setdefault(o.level, []).append(o.ring_m)
        return rings, fps, plan

    rings, fps, plan = client.portal.call(read)
    # the same drawn rectangles, level 1 moved by the registration; the footprint (level 0)
    # and so the placement stay where they were
    lo0 = min(x for r in rings[0] for x, _ in r), min(y for r in rings[0] for _, y in r)
    lo1 = min(x for r in rings[1] for x, _ in r), min(y for r in rings[1] for _, y in r)
    assert (lo1[0] - lo0[0], lo1[1] - lo0[1]) == pytest.approx((-2.0, 3.0))

    # the IFC plan spaces are fitted from the same moved outlines
    def low(rs: list[Any]) -> tuple[float, float]:
        return min(x for r in rs for x, _ in r), min(y for r in rs for _, y in r)

    for level, mine in rings.items():
        assert low(plan[level]) == pytest.approx(low(mine))
    assert fps[0]["source_floor_level"] == 0
    assert min(x for x, _ in fps[0]["ring_m"]) == pytest.approx(lo0[0], abs=0.01)

    # a conversion that recorded no alignment names level 1 when it ran before the alignment and
    # none when it ran after; one that recorded the current alignment names none; a model
    # without plan spaces never does (#D3)
    async def stale(stats: dict[str, Any], at: datetime = LONG_AGO) -> list[int]:
        model = NS(stats=stats, building_id=uuid.UUID(str(fps[0]["building_id"])), created_at=at)
        async with tenant_session(uuid.UUID(tid), scope="tenant") as db:
            if "now" in stats:
                floor_ids = [f.id for f in await _floors(db, model.building_id)]
                stats = {"plan_fit": {"registration": await registration_used(db, floor_ids)}}
                model.stats = stats
            return await ifc_service.realigned_levels(db, model)

    assert client.portal.call(stale, {"plan_fit": {"iou": 0.4}}) == [1]
    later = datetime.now(UTC) + timedelta(hours=1)
    assert client.portal.call(stale, {"plan_fit": {"iou": 0.4}}, later) == []
    moved = {"plan_fit": {"registration": {}}}
    assert client.portal.call(stale, moved, later) == [1]
    assert client.portal.call(stale, {"now": True}) == []
    assert client.portal.call(stale, {"plan_fit": {"reason": "no outline"}}) == []
    assert client.portal.call(stale, {}) == []

    # nothing changed: nothing decided, nothing queued
    assert _waiting_massing(pid, clear=True) == 0
    second = ctx()
    client.portal.call(reg_pass.run, second)
    assert second.decisions == [] and _waiting_massing(pid) == 0

    # the world is shared by this module's other tests: as it was
    _admin_sql(
        "UPDATE sheet_floors SET registration = NULL WHERE floor_id IN (SELECT f.id FROM floors f"
        " JOIN buildings b ON b.id = f.building_id WHERE b.project_id = :p)",
        {"p": pid},
    )


def _world_grid(pid: str, w_m: float, h_m: float, dx: float, dy: float) -> list[dict[str, Any]]:
    """Grid bubbles around the world's units (the same rectangles on both pages)."""
    [(x0, y0, x1, y1)] = _admin_sql(
        "SELECT min((p->>0)::float), min((p->>1)::float), max((p->>0)::float),"
        " max((p->>1)::float) FROM unit_boundaries ub JOIN units u ON u.id = ub.unit_id,"
        " jsonb_array_elements(ub.polygon_m->'ring') p WHERE u.project_id = :p AND ub.is_current",
        {"p": pid},
    )
    words = []
    for i, x in enumerate((x0, (x0 + x1) / 2, x1)):
        for y in (y0 - 4, max(y1 + 4, y0 + 12)):
            words.append(_bubble(str(i + 1), x + dx, y + dy, w_m, h_m))
    for label, y in (("A", y0), ("B", y1)):
        for x in (x0 - 4, max(x1 + 4, x0 + 12)):
            words.append(_bubble(label, x + dx, y + dy, w_m, h_m))
    return words


async def _floors(db: Any, building_id: uuid.UUID) -> list[Any]:
    from sqlalchemy import select

    from unitforma.tenants.models import Floor

    return list((await db.execute(select(Floor).where(Floor.building_id == building_id))).scalars())
