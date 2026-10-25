"""RFC 9457 problem-details responses for every error the API returns."""

from __future__ import annotations

from fastapi import FastAPI, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


class ProblemError(Exception):
    def __init__(
        self,
        status: int,
        title: str,
        detail: str | None = None,
        type_: str = "about:blank",
        extra: dict | None = None,
    ):
        self.status = status
        self.title = title
        self.detail = detail
        self.type = type_
        # RFC 9457 extension members, e.g. the current row on a 409 (plan §6.4)
        self.extra = extra or {}


def _problem(
    status: int, title: str, detail: str | None = None, type_: str = "about:blank", **extra
):
    body = {"type": type_, "title": title, "status": status}
    if detail:
        body["detail"] = detail
    body.update(extra)
    return JSONResponse(body, status_code=status, media_type="application/problem+json")


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ProblemError)
    async def _pe(_: Request, exc: ProblemError):
        return _problem(exc.status, exc.title, exc.detail, exc.type, **jsonable_encoder(exc.extra))

    @app.exception_handler(HTTPException)
    async def _he(_: Request, exc: HTTPException):
        return _problem(exc.status_code, str(exc.detail) if exc.detail else "Error")

    @app.exception_handler(RequestValidationError)
    async def _ve(_: Request, exc: RequestValidationError):
        return _problem(422, "Validation failed", errors=jsonable_encoder(exc.errors()))
