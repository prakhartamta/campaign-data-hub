"""The one error envelope, and the three handlers that guarantee it.

Every failure leaves the API as `{"error": {code, message, details}}`, whatever raised it, so the
frontend parses one shape instead of FastAPI's default for validation, Starlette's for aborts and
a bare traceback for everything else.
"""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

CODE_BAD_REQUEST = "bad_request"
CODE_NOT_FOUND = "not_found"
CODE_CONFLICT = "conflict"
CODE_VALIDATION = "validation_error"
CODE_INTERNAL = "internal_error"

# The code reported for each status a route raises deliberately. Anything else is a bug on our
# side, so it reports as internal rather than inventing a code from the number.
CODES_BY_STATUS = {
    400: CODE_BAD_REQUEST,
    404: CODE_NOT_FOUND,
    409: CODE_CONFLICT,
    422: CODE_VALIDATION,
}


def envelope(status: int, code: str, message: str, details: object = None) -> JSONResponse:
    """Build the single error shape. `details` is null unless the handler has something to add."""
    return JSONResponse(
        status_code=status,
        content={"error": {"code": code, "message": message, "details": details}},
    )


def register_error_handlers(app: FastAPI) -> None:
    """Attach the three handlers. Each covers a disjoint case, so registration order is free."""

    @app.exception_handler(RequestValidationError)
    async def on_validation_error(request: Request, error: RequestValidationError) -> JSONResponse:
        # jsonable_encoder because a pydantic error can carry the original exception object in
        # ctx, which JSONResponse cannot serialize.
        return envelope(
            422, CODE_VALIDATION, "the request failed validation", jsonable_encoder(error.errors())
        )

    @app.exception_handler(StarletteHTTPException)
    async def on_http_error(request: Request, error: StarletteHTTPException) -> JSONResponse:
        code = CODES_BY_STATUS.get(error.status_code, CODE_INTERNAL)
        return envelope(error.status_code, code, str(error.detail))

    @app.exception_handler(Exception)
    async def on_unexpected_error(request: Request, error: Exception) -> JSONResponse:
        # The message is fixed rather than taken from the exception: a SQLAlchemy or OSError
        # string carries file paths and SQL fragments, and this response is public.
        return envelope(500, CODE_INTERNAL, "the server failed to handle the request")
