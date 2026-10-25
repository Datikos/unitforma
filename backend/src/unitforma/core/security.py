"""Request-level protections shared by all routers."""

from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

STATE_CHANGING = {"POST", "PUT", "PATCH", "DELETE"}
PROTECTED_PREFIXES = ("/api/", "/auth/")


class RequestedWithMiddleware(BaseHTTPMiddleware):
    """CSRF defence for cookie-authenticated JSON APIs (plan §8.3).

    Browsers cannot add a custom header cross-origin without a CORS preflight, which this API
    never grants, so requiring ``X-Requested-With: unitforma`` on state-changing requests blocks
    classic form-post CSRF. Cookies are additionally SameSite=Lax.
    """

    async def dispatch(self, request: Request, call_next):
        if request.method in STATE_CHANGING and request.url.path.startswith(PROTECTED_PREFIXES):
            if request.headers.get("x-requested-with") != "unitforma":
                return JSONResponse(
                    {
                        "type": "about:blank",
                        "title": "Missing X-Requested-With header",
                        "status": 403,
                    },
                    status_code=403,
                    media_type="application/problem+json",
                )
        return await call_next(request)
