"""Generated 3D plan renders (ADR-0017 Decision 3): the plan crop, the Gemini request shape and
its defensive parsing, the request → worker → review → approve / reject flow with its limits;
and the setup checklist (Decision 5) on the publishing world."""

from __future__ import annotations

import asyncio
import base64
import io
import json
import uuid

import httpx
import pytest
from PIL import Image

from tests import test_phase4_publishing as phase4
from tests.test_phase4_publishing import world  # noqa: F401 - module-scoped fixture, rebuilt here
from unitforma.core.settings import get_settings
from unitforma.renders import jobs as render_jobs
from unitforma.renders import service as renders
from unitforma.renders.gemini import GeminiProvider
from unitforma.renders.provider import GeneratedImage, ProviderError

pytestmark = phase4.pytestmark

ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/interactions"


def _png(w: int = 64, h: int = 48, colour=(200, 40, 40)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (w, h), colour).save(buf, format="PNG")
    return buf.getvalue()


def test_crop_whites_out_everything_outside_the_outline():
    """The model must draw this apartment, not its neighbours: the crop is the outline's box plus
    8 % and everything outside the ring is white."""
    ring = [[0.25, 0.25], [0.5, 0.25], [0.5, 0.5], [0.25, 0.5]]
    out = Image.open(io.BytesIO(renders.crop_plan(_png(400, 300), ring)))
    assert out.size == (116, 87)  # (0.52 - 0.23) of 400 by (0.52 - 0.23) of 300
    assert out.getpixel((2, 2)) == (255, 255, 255)  # inside the margin, outside the ring
    assert out.getpixel((58, 43)) == (200, 40, 40)  # the apartment itself
    with pytest.raises(ValueError):
        renders.crop_plan(_png(400, 300), [[0.1, 0.1], [0.1, 0.1], [0.1, 0.1]])


def test_joined_crop_cuts_an_opening_into_the_shared_wall():
    """Two outlines that share a wall: the crop keeps both, and the middle of the shared wall is
    painted white as an open passage (the model follows the drawing, not only the prompt); the
    wall near the corners stays, and outlines that do not touch get no opening."""
    left = [[0.2, 0.2], [0.5, 0.2], [0.5, 0.6], [0.2, 0.6]]
    right = [[0.5, 0.2], [0.8, 0.2], [0.8, 0.6], [0.5, 0.6]]  # shares the x = 0.5 wall
    wall = (0.5, 0.2), (0.5, 0.6)
    assert renders.shared_wall(left, right, 0.01) == wall
    assert renders.shared_wall(left, [[0.6, 0.2], [0.9, 0.2], [0.9, 0.6], [0.6, 0.6]], 0.01) is None
    dark = _png(1000, 1000, (30, 30, 30))
    out = Image.open(io.BytesIO(renders.crop_plan(dark, left, extra_rings=[right])))
    # crop box starts at x = (0.2 - 0.08 * 0.6) * 1000 = 152, y = (0.2 - 0.08 * 0.4) * 1000 = 168
    mid = (500 - 152, 400 - 168)
    assert out.getpixel(mid) == (255, 255, 255)  # the opening
    corner = (mid[0], 220 - 168)
    assert out.getpixel(corner) == (30, 30, 30)  # the wall by the corner stays
    assert out.getpixel((mid[0] - 120, mid[1])) == (30, 30, 30)  # inside the left unit
    single = Image.open(io.BytesIO(renders.crop_plan(dark, left)))
    assert single.getpixel((500 - 176 - 2, 400 - 168)) == (30, 30, 30)  # no gap for one unit


def _provider(handler) -> GeminiProvider:
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return GeminiProvider("k3y", "gemini-nano-banana-2.1", ENDPOINT, 0.0336, client=client)


def test_gemini_request_shape_and_defensive_parsing():
    seen: dict = {}

    def ok(request: httpx.Request) -> httpx.Response:
        seen["headers"] = dict(request.headers)
        seen["body"] = json.loads(request.content)
        data = base64.b64encode(b"PNG!").decode()
        block = {"type": "image", "mime_type": "image/jpeg", "data": data}
        steps = [{"type": "model_output", "content": [block]}]
        return httpx.Response(200, json={"id": "i1", "steps": steps})

    img = asyncio.run(_provider(ok).edit(b"\x89PNG", "image/png", "the prompt"))
    assert img.data == b"PNG!" and img.mime == "image/jpeg" and img.cost_usd == 0.0336
    assert seen["headers"]["x-goog-api-key"] == "k3y"
    body = seen["body"]
    assert body["model"] == "gemini-nano-banana-2.1"
    assert body["input"][0] == {"type": "text", "text": "the prompt"}
    assert body["input"][1]["type"] == "image" and body["input"][1]["mime_type"] == "image/png"
    assert base64.b64decode(body["input"][1]["data"]) == b"\x89PNG"
    assert body["response_format"] == {  # jpeg: the only output type Gemini accepts
        "type": "image",
        "mime_type": "image/jpeg",
        "image_size": "1K",
    }

    def accessor(request):  # the SDK-style accessor wins when present
        out = {"data": base64.b64encode(b"A").decode(), "mime_type": "image/jpeg"}
        return httpx.Response(200, json={"output_image": out})

    img = asyncio.run(_provider(accessor).edit(b"x", "image/png", "p"))
    assert img.data == b"A" and img.mime == "image/jpeg"

    def no_image(request):
        return httpx.Response(200, json={"id": "i2", "steps": []})

    with pytest.raises(ProviderError, match="top-level keys: id, steps"):
        asyncio.run(_provider(no_image).edit(b"x", "image/png", "p"))

    def denied(request):
        return httpx.Response(403, json={"error": {"message": "API key not valid"}})

    with pytest.raises(ProviderError, match="403: API key not valid"):
        asyncio.run(_provider(denied).edit(b"x", "image/png", "p"))
    with pytest.raises(ProviderError, match="empty"):
        GeminiProvider("", "m", ENDPOINT)
    with pytest.raises(ProviderError, match="https"):
        GeminiProvider("k", "m", "http://example.test/v1")


class _Stub:
    name = "stub"
    model = "stub-1"

    def __init__(self):
        self.calls: list[tuple[bytes, str, str]] = []
        self.fail = False

    async def edit(self, image: bytes, mime: str, prompt: str) -> GeneratedImage:
        self.calls.append((image, mime, prompt))
        if self.fail:
            raise ProviderError("quota exhausted")
        return GeneratedImage(_png(32, 24, (10, 200, 10)), "image/png", 0.0336)


def test_render_request_review_approve_reject_and_limits(client, world, monkeypatch):  # noqa: F811
    base, tid, sales = world["base"], world["tenant"]["id"], world["sales"]
    unit = world["units"]["A-00-02"]  # outlined on an approved sheet, no media of its own
    url = f"{base}/units/{unit['id']}/renders"
    media_url = f"{base}/units/{unit['id']}/media"

    # off by default: the list says so and a request is refused
    r = client.get(url, headers=sales)
    assert r.status_code == 200 and r.json()["enabled"] is False and r.json()["items"] == []
    assert client.post(url, headers=sales, json={}).status_code == 409

    settings = get_settings()
    stub = _Stub()
    monkeypatch.setattr(settings, "ai_image_provider", "gemini")
    monkeypatch.setattr(settings, "ai_image_daily_limit", 3)
    monkeypatch.setattr(render_jobs, "get_provider", lambda: stub)

    r = client.post(url, headers=sales, json={"note": "oak floors"})
    assert r.status_code == 202, r.text
    rid = r.json()["id"]
    assert r.json()["status"] == "queued" and r.json()["model"] == settings.ai_image_model
    assert client.post(url, headers=sales, json={}).status_code == 409  # one at a time per unit

    out = client.portal.call(render_jobs.generate, uuid.UUID(tid), uuid.UUID(rid))
    assert out["status"] == "review", out
    [(image, mime, prompt)] = stub.calls
    assert mime == "image/png"
    assert prompt.startswith("Create a photorealistic") and prompt.endswith("oak floors")
    im = Image.open(io.BytesIO(image))
    assert max(im.size) <= 1536 and im.getpixel((1, 1)) == (255, 255, 255)

    data = client.get(url, headers=sales).json()
    assert data["used_today"] == 1 and data["daily_limit"] == 3
    [item] = data["items"]
    assert item["status"] == "review" and item["url"] and float(item["cost_usd"]) == 0.0336
    [gen] = [m for m in client.get(media_url, headers=sales).json() if m["kind"] == "plan_render"]
    assert gen["is_ai_generated"] is True and gen["is_public"] is False
    assert gen["ai_disclosure_text"].startswith("Generated from the floor plan")
    assert gen["id"] == item["media_id"]

    # approve: the media becomes public (and, through the layout code, every twin's)
    r = client.post(f"{base}/renders/{rid}/approve", headers=sales)
    assert r.status_code == 200 and r.json()["status"] == "approved"
    [gen] = [m for m in client.get(media_url, headers=sales).json() if m["kind"] == "plan_render"]
    assert gen["is_public"] is True
    assert client.post(f"{base}/renders/{rid}/approve", headers=sales).status_code == 409
    assert client.post(f"{base}/renders/{rid}/reject", headers=sales).status_code == 409

    # two neighbours joined into one apartment (ADR-0017 E4): the crop covers both outlines, the
    # prompt says so, the image belongs to the first unit and names both
    other = world["units"]["A-00-01"]  # same floor; A-01-01 is not
    r = client.post(url, headers=sales, json={"with_unit_id": world["units"]["A-01-01"]["id"]})
    assert r.status_code == 422, r.text
    r = client.post(url, headers=sales, json={"with_unit_id": other["id"]})
    assert r.status_code == 202, r.text
    assert r.json()["partner_unit_id"] == other["id"] and r.json()["partner_code"] == "A-00-01"
    joined_id = r.json()["id"]
    out = client.portal.call(render_jobs.generate, uuid.UUID(tid), uuid.UUID(joined_id))
    assert out["status"] == "review", out
    (single, _, _), (joined, _, joined_prompt) = stub.calls[0], stub.calls[1]
    assert "joined into one larger apartment" in joined_prompt and "open passage" in joined_prompt
    one, two = Image.open(io.BytesIO(single)).size, Image.open(io.BytesIO(joined)).size
    assert two[0] / two[1] > one[0] / one[1]  # both outlines side by side: a wider crop
    media = client.get(media_url, headers=sales).json()
    assert any("joined with A-00-01" in (m["alt_text"] or "") for m in media)
    r = client.post(f"{base}/renders/{joined_id}/approve", headers=sales)
    assert r.status_code == 200

    # a failing provider leaves a failed row with the reason; the cap counts every request
    stub.fail = True
    r = client.post(url, headers=sales, json={})
    assert r.status_code == 202
    rid2 = r.json()["id"]
    out = client.portal.call(render_jobs.generate, uuid.UUID(tid), uuid.UUID(rid2))
    assert out["status"] == "failed" and "quota exhausted" in out["error"]
    assert client.post(url, headers=sales, json={}).status_code == 429
    r = client.post(f"{base}/renders/{rid2}/reject", headers=sales)
    assert r.status_code == 200 and r.json()["status"] == "rejected" and r.json()["url"] is None
    statuses = [i["status"] for i in client.get(url, headers=sales).json()["items"]]
    assert sorted(statuses) == ["approved", "approved", "rejected"]


def test_setup_checklist_reflects_the_project_state(client, world):  # noqa: F811
    base, pid, pm, adm = world["base"], world["project"]["id"], world["pm"], world["adm"]
    r = client.get(f"{base}/projects/{pid}/setup", headers=pm)
    assert r.status_code == 200, r.text
    d = r.json()
    assert [s["key"] for s in d["steps"]] == [
        "documents",
        "floors",
        "mapping",
        "site_plan",
        "placement",
        "facades",
        "features",
        "gallery",
        "location",
        "prices",
        "architect_model",
        "publish",
    ]
    st = {s["key"]: s for s in d["steps"]}
    assert st["documents"]["status"] == "done" and st["documents"]["count"] == 1, d["steps"]
    assert st["floors"]["status"] == "done" and st["floors"]["count"] == 1
    assert st["mapping"]["status"] == "todo"  # nothing published yet in a fresh world
    assert st["site_plan"]["status"] == "done" and st["placement"]["status"] == "done"
    assert st["facades"]["status"] == "todo" and st["facades"]["link"] == "placement"
    assert st["features"]["status"] == "optional"
    assert st["architect_model"]["status"] == "optional"
    assert "IFC" in st["architect_model"]["detail"]
    assert st["location"]["status"] == "todo" and st["location"]["link"] == "publish"
    assert st["publish"]["status"] == "attention"
    assert d["total"] == 12 and d["done"] == sum(1 for s in d["steps"] if s["status"] == "done")

    proj = client.get(f"{base}/projects/{pid}", headers=adm).json()
    r = client.patch(
        f"{base}/projects/{pid}",
        headers=adm,
        json={
            "address": {**(proj["address"] or {}), "lat": 41.7, "lng": 44.8},
            "version": proj["version"],
        },
    )
    assert r.status_code == 200, r.text
    again = client.get(f"{base}/projects/{pid}/setup", headers=pm).json()
    st = {s["key"]: s for s in again["steps"]}
    assert st["location"]["status"] == "done" and st["location"]["detail"] == "41.7, 44.8"


def test_workspace_render_prompt_replaces_the_base_text(client, world, monkeypatch):  # noqa: F811
    """ADR-0023: the tenant admin sets one base prompt for the workspace; the next request starts
    with it, the joined sentence and the note are still appended; blank resets to the default."""
    base, tid, adm, sales = world["base"], world["tenant"]["id"], world["adm"], world["sales"]
    url = f"{base}/render-prompt"

    r = client.get(url, headers=adm)
    assert r.status_code == 200, r.text
    assert r.json() == {"default": renders.PROMPT, "prompt": None, "source": "default"}
    assert client.get(url, headers=sales).status_code == 403
    assert client.put(url, headers=sales, json={"prompt": "x"}).status_code == 403
    assert client.put(url, headers=adm, json={"prompt": "x" * 4001}).status_code == 422

    custom = "Render a bright Scandinavian apartment seen from above at 30 degrees."
    r = client.put(url, headers=adm, json={"prompt": f"  {custom}\n"})
    assert r.status_code == 200 and r.json()["prompt"] == custom
    assert r.json()["source"] == "workspace" and r.json()["default"] == renders.PROMPT

    # PATCH /tenants/{id} with another settings key keeps the prompt (merge, not replace)
    r = client.patch(f"{base}", headers=adm, json={"settings": {"other": 1}})
    assert r.status_code == 200 and r.json()["settings"]["render_prompt"] == custom
    assert r.json()["settings"]["other"] == 1

    settings = get_settings()
    stub = _Stub()
    monkeypatch.setattr(settings, "ai_image_provider", "gemini")
    monkeypatch.setattr(render_jobs, "get_provider", lambda: stub)
    unit = world["units"]["A-00-02"]
    other = world["units"]["A-00-01"]
    r = client.post(
        f"{base}/units/{unit['id']}/renders",
        headers=sales,
        json={"note": "marble kitchen", "with_unit_id": other["id"]},
    )
    assert r.status_code == 202, r.text
    out = client.portal.call(render_jobs.generate, uuid.UUID(tid), uuid.UUID(r.json()["id"]))
    assert out["status"] == "review", out
    [(_, _, prompt)] = stub.calls
    assert prompt.startswith(custom) and "Create a photorealistic" not in prompt
    assert "joined into one larger apartment" in prompt and prompt.endswith("marble kitchen")

    r = client.put(url, headers=adm, json={"prompt": "   "})
    assert r.status_code == 200 and r.json() == {
        "default": renders.PROMPT,
        "prompt": None,
        "source": "default",
    }
    audit = client.get(f"{base}/audit", headers=adm, params={"entity_type": "tenant"}).json()
    actions = [a["action"] for a in audit["items"]]
    assert actions.count("render_prompt") == 2
