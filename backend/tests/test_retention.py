"""The retention sweep (ADR-0021) on the publishing world: it removes only what nobody can reach any
more, keeps everything younger than its grace period, and the dry run counts without deleting."""

from __future__ import annotations

import os
import time
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

from tests import test_phase4_publishing as phase4
from tests.test_phase4_publishing import _admin_sql, world  # noqa: F401 - module-scoped fixture

pytestmark = phase4.pytestmark

DAY = 86400


def _file(root: Path, key: str, age_days: float, data: bytes = b"x") -> Path:
    p = root / key
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(data)
    t = time.time() - age_days * DAY
    os.utime(p, (t, t))
    return p


def _intent(client, base, headers, pid, title):
    doc = client.post(
        f"{base}/projects/{pid}/documents", headers=headers, json={"kind": "other", "title": title}
    ).json()
    up = client.post(
        f"{base}/documents/{doc['id']}/uploads",
        headers=headers,
        json={"file_name": "f.pdf", "content_type": "application/pdf", "byte_size": 3},
    ).json()
    return doc, up["revision"]


def test_sweep_removes_only_what_nobody_can_reach(client, world, monkeypatch):  # noqa: F811
    from unitforma.core.settings import get_settings
    from unitforma.housekeeping.service import sweep

    s = get_settings()
    root = Path(s.storage_local_root)
    base, pm = world["base"], world["pm"]
    tid, pid = world["tenant"]["id"], world["project"]["id"]
    # a live publication, so pub/ holds referenced assets
    r = client.put(
        f"{base}/projects/{pid}/units/publication",
        headers=pm,
        json={"status": "published", "all_active": True},
    )
    assert r.status_code == 200, r.text
    r = client.post(f"{base}/projects/{pid}/publications", headers=pm, json={"mode": "publish"})
    assert r.status_code == 201, r.text

    # a dead upload intent two days old (with its object), a fresh one that must stay
    dead_doc, dead_rev = _intent(client, base, pm, pid, "never completed")
    _admin_sql(
        "UPDATE document_revisions SET created_at = now() - interval '2 days' WHERE id = :id",
        {"id": dead_rev["id"]},
    )
    _admin_sql(
        "UPDATE documents SET created_at = now() - interval '2 days' WHERE id = :id",
        {"id": dead_doc["id"]},
    )
    fresh_doc, fresh_rev = _intent(client, base, pm, pid, "still uploading")

    # an expired invitation and an expired token, long past their grace periods; a live token stays
    inv_old, inv_new = uuid.uuid4(), uuid.uuid4()
    now = datetime.now(UTC)
    for iid, days in ((inv_old, 40), (inv_new, 2)):
        _admin_sql(
            "INSERT INTO staff_invitations (id, tenant_id, email, role, project_ids, token_hash, "
            "expires_at, created_at, updated_at) VALUES (:id, :t, :e, 'viewer', '{}', :h, :exp, "
            "now(), now())",
            {
                "id": iid,
                "t": tid,
                "e": f"{iid.hex[:8]}@example.com",
                "h": iid.hex,
                "exp": now - timedelta(days=days),
            },
        )
    [(user_id,)] = _admin_sql("SELECT id FROM users ORDER BY created_at LIMIT 1")
    tok_old, tok_live = uuid.uuid4(), uuid.uuid4()
    for tok, days in ((tok_old, -100), (tok_live, 100)):
        _admin_sql(
            "INSERT INTO api_tokens (id, tenant_id, user_id, name, token_prefix, token_hash, "
            "scope, expires_at, created_at) VALUES (:id, :t, :u, 'n', :p, :h, 'read', :exp, now())",
            {
                "id": tok,
                "t": tid,
                "u": user_id,
                "p": tok.hex[:8],
                "h": tok.hex,
                "exp": now + timedelta(days=days),
            },
        )

    # a render crop of a render finished 40 days ago; one finished yesterday keeps its crop
    unit = next(iter(world["units"].values()))
    crops = {}
    for age in (40, 1):
        rid = uuid.uuid4()
        key = f"t/{tid}/p/{pid}/renders/{unit['id']}/{rid.hex[:12]}-plan.png"
        _file(root, key, age)
        _admin_sql(
            "INSERT INTO unit_renders (id, tenant_id, project_id, unit_id, status, provider, "
            "model, prompt, input_key, created_at, finished_at) VALUES (:id, :t, :p, :u, "
            "'approved', 'test', 'm', 'p', :k, :at, :at)",
            {
                "id": rid,
                "t": tid,
                "p": pid,
                "u": unit["id"],
                "k": key,
                "at": now - timedelta(days=age),
            },
        )
        crops[age] = (rid, key)

    # an orphaned project prefix: old goes, fresh stays; the living project's files stay
    orphan_old = f"t/{tid}/p/{uuid.uuid4()}/documents/{uuid.uuid4()}/f.pdf"
    orphan_new = f"t/{tid}/p/{uuid.uuid4()}/documents/{uuid.uuid4()}/f.pdf"
    _file(root, orphan_old, 10)
    _file(root, orphan_new, 1)
    living = [p for p in (root / f"t/{tid}/p/{pid}/documents").rglob("*") if p.is_file()]
    assert living
    orphan_doc = f"t/{tid}/p/{pid}/documents/{uuid.uuid4()}/f.pdf"
    _file(root, orphan_doc, 10)

    # under pub/: a referenced asset backdated stays, a stray old one goes, a stray fresh one stays
    [(assets,)] = _admin_sql(
        "SELECT assets FROM publications WHERE project_id = :p AND status = 'published'", {"p": pid}
    )
    referenced = root / next(iter(assets.values()))
    assert referenced.is_file()
    old = time.time() - 45 * DAY
    os.utime(referenced, (old, old))
    stray_old = _file(root, f"pub/{tid}/{pid}/deadbeef.webp", 45)
    stray_new = _file(root, f"pub/{tid}/{pid}/fresh.webp", 1)
    pub_orphan = _file(root, f"pub/{tid}/{uuid.uuid4()}/x.webp", 10)

    # dry run first: everything counted, nothing gone
    monkeypatch.setattr(s, "retention_enabled", False)
    dry = client.portal.call(sweep)
    # the sweep is platform-wide, so other modules' leftovers may add to the counts
    assert dry["pending_uploads"] >= 2 and dry["render_inputs"] >= 1 and dry["retired_assets"] >= 1
    assert dry["invitations"] >= 1 and dry["api_tokens"] >= 1 and dry["orphan_prefixes"] >= 3
    assert stray_old.is_file() and (root / crops[40][1]).is_file() and (root / orphan_old).is_file()
    assert _admin_sql("SELECT 1 FROM documents WHERE id = :id", {"id": dead_doc["id"]})

    monkeypatch.setattr(s, "retention_enabled", True)
    counts = client.portal.call(sweep)
    assert counts == dry, counts

    # gone
    assert not _admin_sql("SELECT 1 FROM document_revisions WHERE id = :id", {"id": dead_rev["id"]})
    assert not _admin_sql("SELECT 1 FROM documents WHERE id = :id", {"id": dead_doc["id"]})
    assert not _admin_sql("SELECT 1 FROM staff_invitations WHERE id = :id", {"id": inv_old})
    assert not _admin_sql("SELECT 1 FROM api_tokens WHERE id = :id", {"id": tok_old})
    assert not (root / crops[40][1]).exists()
    [(k,)] = _admin_sql("SELECT input_key FROM unit_renders WHERE id = :id", {"id": crops[40][0]})
    assert k is None
    assert not (root / orphan_old).exists() and not (root / orphan_doc).exists()
    assert not stray_old.exists() and not pub_orphan.exists()
    # kept
    assert _admin_sql("SELECT 1 FROM document_revisions WHERE id = :id", {"id": fresh_rev["id"]})
    assert _admin_sql("SELECT 1 FROM documents WHERE id = :id", {"id": fresh_doc["id"]})
    assert _admin_sql("SELECT 1 FROM staff_invitations WHERE id = :id", {"id": inv_new})
    assert _admin_sql("SELECT 1 FROM api_tokens WHERE id = :id", {"id": tok_live})
    assert (root / crops[1][1]).is_file()
    assert (root / orphan_new).is_file() and all(p.is_file() for p in living)
    assert referenced.is_file() and stray_new.is_file()
    # a second run finds nothing
    again = client.portal.call(sweep)
    assert all(v == 0 for v in again.values()), again

    # leave the world as it was for the other modules
    _admin_sql("DELETE FROM api_tokens WHERE id = :id", {"id": tok_live})
    _admin_sql("DELETE FROM staff_invitations WHERE id = :id", {"id": inv_new})
    _admin_sql("DELETE FROM unit_renders WHERE id = :id", {"id": crops[1][0]})
    client.delete(f"{base}/documents/{fresh_doc['id']}", headers=pm)
