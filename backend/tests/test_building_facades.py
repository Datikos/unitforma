"""Facade assignments live on the building (ADR-0016 E3): ``PATCH /buildings/{id}`` with
``facades`` validates and stores them, the footprint endpoint and the massing read the column,
the legacy ``site_frame.facades`` shape of the previous release still reads, and every write is
mirrored there for one release."""

from __future__ import annotations

import uuid

from tests import test_phase4_publishing as phase4
from tests.pdf_fixture import make_section_pdf
from tests.test_phase4_publishing import _upload, world  # noqa: F401 - module-scoped fixture
from unitforma.geometry import massing

pytestmark = phase4.pytestmark


def test_facades_on_the_building_and_the_legacy_site_frame_still_reads(client, world):  # noqa: F811
    from unitforma.geometry.jobs import build_massing

    base, pid, tid, adm = world["base"], world["project"]["id"], world["tenant"]["id"], world["adm"]
    b = next(
        x
        for x in client.get(f"{base}/projects/{pid}/buildings", headers=adm).json()
        if x["code"] == "A"
    )
    [sheet] = _upload(
        client, base, adm, pid, "elevation", "Facade 1-10", make_section_pdf(), tid, b["id"]
    )
    region = {"ring": [[0.1, 0.2], [0.9, 0.2], [0.9, 0.8], [0.1, 0.8]]}
    r = client.patch(
        f"{base}/buildings/{b['id']}",
        headers=adm,
        json={
            "facades": [{"side": 0, "sheet_id": sheet["id"], "region": region, "flip": False}],
            "version": b["version"],
        },
    )
    assert r.status_code == 200, r.text
    b = r.json()
    assert b["facades"] == [{"side": 0, "sheet_id": sheet["id"], "region": region, "flip": False}]
    fp = next(
        f
        for f in client.get(f"{base}/projects/{pid}/footprints", headers=adm).json()
        if f["building_id"] == b["id"]
    )
    assert [a["side"] for a in fp["facades"]] == [0]

    # the massing carries the drawing read from the column
    res = client.portal.call(build_massing, uuid.UUID(tid), uuid.UUID(pid))
    assert res["status"] == "ready", res
    m = client.get(f"{base}/projects/{pid}/massing", headers=adm).json()
    gltf, _ = massing.parse_glb(client.get(m["glb_url"]).content)
    assert len(gltf["images"]) == 1

    # validation: one drawing per side, a sheet of this project, sides 0 to 3
    bad = [
        [{"side": 0, "sheet_id": sheet["id"]}, {"side": 0, "sheet_id": sheet["id"]}],
        [{"side": 1, "sheet_id": str(uuid.uuid4())}],
        [{"side": 4, "sheet_id": sheet["id"]}],
    ]
    for facades in bad:
        r = client.patch(
            f"{base}/buildings/{b['id']}",
            headers=adm,
            json={"facades": facades, "version": b["version"]},
        )
        assert r.status_code == 422, (facades, r.text)

    # the previous release wrote the choices into the project's site frame: a building whose
    # column is still null reads them (hosts that skipped the 0015 backfill, old writers)
    phase4._admin_sql("UPDATE buildings SET facades = NULL WHERE id = :id", {"id": b["id"]})
    proj = client.get(f"{base}/projects/{pid}", headers=adm).json()
    legacy = {b["id"]: [{"side": 2, "sheet_id": sheet["id"], "region": None, "flip": True}]}
    r = client.patch(
        f"{base}/projects/{pid}",
        headers=adm,
        json={
            "site_frame": {**(proj["site_frame"] or {}), "facades": legacy},
            "version": proj["version"],
        },
    )
    assert r.status_code == 200, r.text
    fp = next(
        f
        for f in client.get(f"{base}/projects/{pid}/footprints", headers=adm).json()
        if f["building_id"] == b["id"]
    )
    assert [(a["side"], a["flip"]) for a in fp["facades"]] == [(2, True)]

    # this release mirrors its writes there too, so the previous release keeps reading them
    b = next(
        x
        for x in client.get(f"{base}/projects/{pid}/buildings", headers=adm).json()
        if x["id"] == b["id"]
    )
    r = client.patch(
        f"{base}/buildings/{b['id']}",
        headers=adm,
        json={"facades": [{"side": 1, "sheet_id": sheet["id"]}], "version": b["version"]},
    )
    assert r.status_code == 200, r.text
    proj = client.get(f"{base}/projects/{pid}", headers=adm).json()
    assert [a["side"] for a in proj["site_frame"]["facades"][b["id"]]] == [1]

    # once the column is written, it wins, even empty (clearing works)
    r = client.patch(
        f"{base}/buildings/{b['id']}",
        headers=adm,
        json={"facades": [], "version": r.json()["version"]},
    )
    assert r.status_code == 200 and r.json()["facades"] == []
    fp = next(
        f
        for f in client.get(f"{base}/projects/{pid}/footprints", headers=adm).json()
        if f["building_id"] == b["id"]
    )
    assert fp["facades"] == []
