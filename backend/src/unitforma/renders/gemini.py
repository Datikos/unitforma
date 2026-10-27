"""Gemini image editing over REST (ADR-0017 Decision 4).

Request shape from ai.google.dev/gemini-api/docs/image-generation as read on 2026-10-26 (plan §21):
``POST {endpoint}`` with ``x-goog-api-key``, a body of ``model``, ``input`` blocks (text and a
base64 image with ``mime_type``) and ``response_format`` asking for an image. The raw JSON answer
is not documented on that page (the SDK exposes ``output_image.data``; the REST answer carries
``steps[]`` with ``{"type": "image", "data": ...}`` blocks), so the parser walks the answer for the
last image block and reports the top-level keys when it finds none.
"""

from __future__ import annotations

import base64
from typing import Any
from urllib.parse import urlsplit

import httpx

from unitforma.renders.provider import GeneratedImage, ProviderError


class GeminiProvider:
    name = "gemini"

    def __init__(
        self,
        api_key: str,
        model: str,
        endpoint: str,
        cost_per_image: float | None = None,
        timeout: float = 120.0,
        client: httpx.AsyncClient | None = None,
    ):
        if not api_key:
            raise ProviderError("UF_AI_IMAGE_API_KEY is empty: mount the secret file")
        if urlsplit(endpoint).scheme != "https":
            raise ProviderError("UF_AI_IMAGE_ENDPOINT must be an https URL")
        self.model = model
        self.endpoint = endpoint
        self.cost_per_image = cost_per_image
        self.timeout = timeout
        self._api_key = api_key
        self._client = client

    async def edit(self, image: bytes, mime: str, prompt: str) -> GeneratedImage:
        body = {
            "model": self.model,
            "input": [
                {"type": "text", "text": prompt},
                {"type": "image", "mime_type": mime, "data": base64.b64encode(image).decode()},
            ],
            # no aspect_ratio: the model keeps the proportions of the drawing it was given. Only
            # image/jpeg is accepted here (live answer of 2026-10-26: "The value 'image/png' is not
            # supported for 'response_format.mime_type'. Supported values: 'image/jpeg'").
            "response_format": {"type": "image", "mime_type": "image/jpeg", "image_size": "1K"},
        }
        headers = {"x-goog-api-key": self._api_key, "Content-Type": "application/json"}
        try:
            if self._client is not None:
                r = await self._client.post(self.endpoint, json=body, headers=headers)
            else:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    r = await client.post(self.endpoint, json=body, headers=headers)
        except httpx.HTTPError as e:
            raise ProviderError(f"gemini request failed: {type(e).__name__}") from e
        if r.status_code >= 400:
            raise ProviderError(f"gemini answered {r.status_code}: {_safe_text(r)}")
        try:
            payload = r.json()
        except ValueError as e:
            raise ProviderError("gemini answered with a body that is not JSON") from e
        found = _find_image(payload)
        if found is None:
            keys = (
                ", ".join(sorted(payload)[:12])
                if isinstance(payload, dict)
                else type(payload).__name__
            )
            raise ProviderError(f"gemini answered without an image block (top-level keys: {keys})")
        data_b64, out_mime = found
        try:
            data = base64.b64decode(data_b64, validate=True)
        except ValueError as e:
            raise ProviderError("gemini image block is not valid base64") from e
        return GeneratedImage(data, out_mime or "image/jpeg", self.cost_per_image)

    async def describe(self, image: bytes, mime: str, prompt: str) -> str:
        """Text answer to a question about one image (ADR-0025 Decision 5, "classify"). The raw
        shape of a text answer is not documented on the pages read for ADR-0017 (plan §21): the
        parser takes the last text block of the answer and reports the keys when there is none."""
        body = {
            "model": self.model,
            "input": [
                {"type": "text", "text": prompt},
                {"type": "image", "mime_type": mime, "data": base64.b64encode(image).decode()},
            ],
            "response_format": {"type": "text"},
        }
        headers = {"x-goog-api-key": self._api_key, "Content-Type": "application/json"}
        try:
            if self._client is not None:
                r = await self._client.post(self.endpoint, json=body, headers=headers)
            else:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    r = await client.post(self.endpoint, json=body, headers=headers)
        except httpx.HTTPError as e:
            raise ProviderError(f"gemini request failed: {type(e).__name__}") from e
        if r.status_code >= 400:
            raise ProviderError(f"gemini answered {r.status_code}: {_safe_text(r)}")
        try:
            payload = r.json()
        except ValueError as e:
            raise ProviderError("gemini answered with a body that is not JSON") from e
        text = _find_text(payload)
        if text is None:
            keys = (
                ", ".join(sorted(payload)[:12])
                if isinstance(payload, dict)
                else type(payload).__name__
            )
            raise ProviderError(f"gemini answered without a text block (top-level keys: {keys})")
        return text.strip()


def _find_text(node: Any) -> str | None:
    """``output_text`` when present, else the last ``{"type": "text", "text"}`` block or legacy
    ``parts[].text`` anywhere in the answer, skipping the echoed request."""
    if isinstance(node, dict):
        if isinstance(node.get("output_text"), str):
            return node["output_text"]
        if node.get("type") == "text" and isinstance(node.get("text"), str):
            return node["text"]
        if isinstance(node.get("text"), str) and set(node) <= {"text", "thought"}:
            return node["text"]
        last = None
        for k, v in node.items():
            if k == "input":
                continue
            f = _find_text(v)
            if f is not None:
                last = f
        return last
    if isinstance(node, list):
        last = None
        for v in node:
            f = _find_text(v)
            if f is not None:
                last = f
        return last
    return None


def _safe_text(r: httpx.Response) -> str:
    """The first 300 characters of an error body; the vendor's message, never the key."""
    try:
        err = r.json().get("error", {})
        return str(err.get("message") or err)[:300]
    except Exception:  # noqa: BLE001 - any body shape
        return r.text[:300]


def _find_image(node: Any) -> tuple[str, str | None] | None:
    """``output_image.data`` when present, else the last image block anywhere in the answer:
    ``{"type": "image", "data"}`` (interactions) or ``{"inline_data": {"data"}}`` (legacy)."""
    if isinstance(node, dict):
        oi = node.get("output_image")
        if isinstance(oi, dict) and isinstance(oi.get("data"), str):
            return oi["data"], oi.get("mime_type") or oi.get("mimeType")
        if node.get("type") == "image" and isinstance(node.get("data"), str):
            return node["data"], node.get("mime_type") or node.get("mimeType")
        inline = node.get("inline_data") or node.get("inlineData")
        if isinstance(inline, dict) and isinstance(inline.get("data"), str):
            return inline["data"], inline.get("mime_type") or inline.get("mimeType")
        last = None
        for v in node.values():
            f = _find_image(v)
            if f is not None:
                last = f
        return last
    if isinstance(node, list):
        last = None
        for v in node:
            f = _find_image(v)
            if f is not None:
                last = f
        return last
    return None
