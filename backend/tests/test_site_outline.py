"""ADR-0035 Decisions 1 and 2: a placed building is drawn with the site plan's own outline.

The choice of face (pure), when a stored outline is stale (pure), and on the publishing world:
saving a placement queues the massing, the massing job stores the outline, the footprint API
returns it and a later transform makes it stale again."""

from __future__ import annotations

import os
import uuid
from types import SimpleNamespace as NS

import pytest
from shapely.geometry import Polygon, box
from shapely.ops import unary_union
from sqlalchemy import create_engine, text

from tests import test_phase4_publishing as phase4
from tests.test_phase4_publishing import world  # noqa: F401 - module-scoped fixture, rebuilt here
from unitforma.geometry import site_outline as so

# N4's shape in miniature: a wing (0-10 × 0-30) and a bar (14-60 × 20-30), a 4 m stair core
# between them that no unit covers, so the union is two parts and the hull covers the courtyard
WING, BAR = box(0, 0, 10, 30), box(14, 20, 60, 30)
UNITS = unary_union([WING, BAR])
ENVELOPE = Polygon([(0, 0), (10, 0), (10, 20), (60, 20), (60, 30), (0, 30)])
PLOT = box(-20, -20, 90, 60)


def test_the_envelope_is_chosen_over_the_plot_and_a_part():
    hull = UNITS.convex_hull
    assert UNITS.geom_type == "MultiPolygon" and hull.area > ENVELOPE.area * 1.1
    found = so.drawn_outline(UNITS, hull, [PLOT, BAR, ENVELOPE])
    assert found is not None
    face, cover = found
    assert face.equals(ENVELOPE) and cover == pytest.approx(1.0)


def test_no_outline_when_only_the_plot_holds_the_units():
    # the plot is far larger than the footprint: drawing it would be wrong, the hull stays
    assert so.drawn_outline(UNITS, UNITS.convex_hull, [PLOT, BAR]) is None


def test_placed_moves_and_turns_by_the_site_transform():
    moved = so.placed(box(0, 0, 2, 1), {"tx": 10, "ty": 5, "rotation_deg": 90})
    minx, miny, maxx, maxy = moved.bounds
    assert (round(minx, 6), round(miny, 6), round(maxx, 6), round(maxy, 6)) == (9, 5, 10, 7)


def _stored(transform):
    return {
        "v": 1,
        "sheet_id": "s1",
        "m_per_px": 0.05,
        "transform": so._transform_key(transform),
        "ring": [[0, 0], [1, 0], [1, 1]],
    }


def test_a_stored_outline_is_read_only_while_sheet_scale_and_transform_match():
    t = {"tx": 1.0, "ty": 2.0, "rotation_deg": 0.0, "scale": 1.0}
    sheet = NS(id="s1", calibration={"m_per_px": 0.05})
    b = NS(site_outline=_stored(t), site_transform=t, placement_status="confirmed")
    assert so.current_ring(b, sheet) == [[0, 0], [1, 0], [1, 1]]
    assert so.current_ring(NS(**{**vars(b), "site_transform": {**t, "tx": 1.5}}), sheet) is None
    assert so.current_ring(NS(**{**vars(b), "site_transform": {**t, "scale": 1.1}}), sheet) is None
    assert so.current_ring(b, NS(id="s1", calibration={"m_per_px": 0.06})) is None
    assert so.current_ring(b, NS(id="s2", calibration={"m_per_px": 0.05})) is None
    assert so.current_ring(NS(**{**vars(b), "placement_status": "unplaced"}), sheet) is None
    assert so.current_ring(b, None) is None


pytestmark_db = phase4.pytestmark


def _waiting_massing(project_id: str, clear: bool = False) -> int:
    """Waiting ``geometry.build_massing`` jobs of the project (one at most: queueing lock);
    ``clear`` deletes them first, so the next step shows whether it queued one."""
    eng = create_engine(os.environ["UF_TEST_DATABASE_ADMIN_URL"])
    with eng.begin() as conn:
        if clear:
            conn.execute(
                text(
                    "DELETE FROM procrastinate_jobs WHERE task_name = 'geometry.build_massing'"
                    " AND status = 'todo' AND args->>'project_id' = :p"
                ),
                {"p": project_id},
            )
        n = conn.execute(
            text(
                "SELECT count(*) FROM procrastinate_jobs WHERE task_name = 'geometry.build_massing'"
                " AND status = 'todo' AND args->>'project_id' = :p"
            ),
            {"p": project_id},
        ).scalar_one()
    eng.dispose()
    return int(n)


@pytestmark_db
def test_the_massing_job_stores_the_outline_and_a_new_placement_drops_it(
    client,
    world,  # noqa: F811
    monkeypatch,
):
    from unitforma.geometry.jobs import build_massing

    base, pid, adm, tid = world["base"], world["project"]["id"], world["adm"], world["tenant"]["id"]
    fp = client.get(f"{base}/projects/{pid}/footprints", headers=adm).json()[0]
    assert fp["placement_status"] == "confirmed" and fp["site_outline_m"] is None

    # the site plan draws the building 5 % larger than its units, next to the plot outline
    t = fp["site_transform"]
    units_site = so.placed(Polygon(fp["ring_m"]), t)
    envelope = units_site.buffer(0.5, join_style=2)
    monkeypatch.setattr(
        so, "site_faces", lambda sheet: [box(*envelope.bounds).buffer(80), envelope]
    )
    out = client.portal.call(build_massing, uuid.UUID(tid), uuid.UUID(pid))
    assert out["status"] == "ready"
    fp = client.get(f"{base}/projects/{pid}/footprints", headers=adm).json()[0]
    assert fp["site_outline_m"] and Polygon(fp["site_outline_m"]).area == pytest.approx(
        envelope.area, rel=1e-3
    )

    # moving the building makes the stored outline stale at once and queues the massing
    assert _waiting_massing(pid, clear=True) == 0
    r = client.patch(
        f"{base}/buildings/{fp['building_id']}",
        headers=adm,
        json={"site_transform": {**t, "tx": float(t["tx"]) + 1}, "version": fp["version"]},
    )
    assert r.status_code == 200, r.text
    assert _waiting_massing(pid) == 1
    fp = client.get(f"{base}/projects/{pid}/footprints", headers=adm).json()[0]
    assert fp["site_outline_m"] is None

    # a rename queues nothing; the world's placement is restored for the other modules
    r = client.patch(
        f"{base}/buildings/{fp['building_id']}",
        headers=adm,
        json={"site_transform": t, "version": fp["version"]},
    )
    assert r.status_code == 200, r.text
    assert _waiting_massing(pid, clear=True) == 0
    fp = client.get(f"{base}/projects/{pid}/footprints", headers=adm).json()[0]
    r = client.patch(
        f"{base}/buildings/{fp['building_id']}",
        headers=adm,
        json={"name": "Block A", "version": fp["version"]},
    )
    assert r.status_code == 200, r.text
    assert _waiting_massing(pid) == 0
