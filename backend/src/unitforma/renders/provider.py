"""The image provider behind generated 3D plan renders (ADR-0017 Decision 4).

One interface, one configured implementation. ``get_provider()`` returns ``None`` when
``UF_AI_IMAGE_PROVIDER`` is ``none`` (the default), which hides the feature in the admin app.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class GeneratedImage:
    data: bytes
    mime: str
    cost_usd: float | None = None


class ProviderError(Exception):
    """The provider refused or answered in an unexpected shape. The message holds no secret and is
    stored on the request so the reviewer sees why nothing came back."""


class ImageProvider(Protocol):
    name: str
    model: str

    async def edit(self, image: bytes, mime: str, prompt: str) -> GeneratedImage:
        """One image in (the plan crop), one image out, following ``prompt``."""
        ...


def get_provider() -> ImageProvider | None:
    from unitforma.core.settings import get_settings

    s = get_settings()
    if s.ai_image_provider == "gemini":
        from unitforma.renders.gemini import GeminiProvider

        return GeminiProvider(
            api_key=s.ai_image_api_key,
            model=s.ai_image_model,
            endpoint=s.ai_image_endpoint,
            cost_per_image=s.ai_image_cost_per_image_usd,
        )
    return None
