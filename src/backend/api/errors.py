# Map exceptions to one error envelope: {"error": {"code", "message", "request_id"}}
import logging
import math

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from backend.limits import RateLimitedError
from backend.gate import AiTimeoutError, BusyError
from backend.api.deps import clear_auth_cookie, OriginNotAllowedError
from backend.ports import (
    AccountLockedError, ConversationError, EmailTakenError, InvalidCredentialsError,
    SessionConflictError, UnauthenticatedError, WrongPasswordError, InvalidProfileError
)
from retrieval.profiles import InvalidConstraintError, UnsupportedConstraintError, UnverifiableConstraintError

log = logging.getLogger(__name__)


def _error(
    request: Request, status: int, code: str, message: str, headers: dict[str, str] | None = None
) -> JSONResponse:
    request_id = getattr(request.state, "request_id", None)
    headers = dict(headers or {})
    if request_id:
        headers["X-Request-ID"] = request_id
    return JSONResponse(
        status_code=status,
        content={"error": {"code": code, "message": message, "request_id": request_id}},
        headers=headers,
    )


def _validation_message(exc: RequestValidationError) -> str:
    # Field path and rule only. Never echo the input: it may be the user's message
    parts = []
    for item in exc.errors()[:5]:
        field = ".".join(str(p) for p in item["loc"][1:]) or "body"
        parts.append(f"{field}: {item['msg']}")
    return "; ".join(parts)


def unexpected_error_response(request: Request, exc: Exception) -> JSONResponse:
    request_id = getattr(request.state, "request_id", None)
    log.error("unhandled error request_id=%s", request_id, exc_info=exc)
    # Generic text: exception messages can leak internals
    return _error(request, 500, "internal_error", "Something went wrong")


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(InvalidConstraintError)
    async def invalid_constraint(request: Request, exc: InvalidConstraintError):
        return _error(request, 422, 'invalid_constraint', str(exc))

    @app.exception_handler(UnsupportedConstraintError)
    async def unsupported_constraint(request: Request, exc: UnsupportedConstraintError):
        code = 'unverifiable_constraint' if isinstance(exc, UnverifiableConstraintError) else 'unsupported_constraint'
        return _error(request, 422, code, str(exc))

    @app.exception_handler(RequestValidationError)
    async def validation(request: Request, exc: RequestValidationError):
        return _error(request, 422, "validation_error", _validation_message(exc))

    @app.exception_handler(ConversationError)
    async def conversation(request: Request, exc: ConversationError):
        return _error(request, 422, "invalid_request", "The request could not be processed")

    @app.exception_handler(SessionConflictError)
    async def conflict(request: Request, exc: SessionConflictError):
        return _error(request, 409, "session_conflict", "Session changed, please retry")

    @app.exception_handler(BusyError)
    async def busy(request: Request, exc: BusyError):
        return _error(request, 503, "busy", "Server is busy, please retry", {"Retry-After": "2"})

    @app.exception_handler(AiTimeoutError)
    async def timeout(request: Request, exc: AiTimeoutError):
        return _error(request, 504, "timeout", "The request took too long, please retry")

    @app.exception_handler(EmailTakenError)
    async def email_taken(request: Request, exc: EmailTakenError):
        return _error(request, 409, "email_taken", "This email is already registered")

    @app.exception_handler(InvalidCredentialsError)
    async def invalid_credentials(request: Request, exc: InvalidCredentialsError):
        return _error(request, 401, "invalid_credentials", "Email or password is incorrect")

    @app.exception_handler(WrongPasswordError)
    async def wrong_password(request: Request, exc: WrongPasswordError):
        return _error(request, 403, "wrong_password", "Current password is incorrect")

    async def rate_limited(request: Request, exc: AccountLockedError | RateLimitedError):
        seconds = max(1, math.ceil(exc.retry_after.total_seconds()))
        return _error(
            request, 429, "rate_limited", "Too many attempts, please try later",
            {"Retry-After": str(seconds)},
        )

    # One answer for a locked account and for a flooding IP
    for exc_type in (AccountLockedError, RateLimitedError):
        app.add_exception_handler(exc_type, rate_limited)

    @app.exception_handler(OriginNotAllowedError)
    async def origin_not_allowed(request: Request, exc: OriginNotAllowedError):
        return _error(request, 403, "forbidden_origin", "Request origin is not allowed")

    @app.exception_handler(UnauthenticatedError)
    async def unauthenticated(request: Request, exc: UnauthenticatedError):
        response = _error(request, 401, "unauthenticated", "Sign in required")
        clear_auth_cookie(response)  # a stale or forged cookie must not linger
        return response
    
    @app.exception_handler(InvalidProfileError)
    async def invalid_profile(request: Request, exc: InvalidProfileError):
        return _error(request, 422, "validation_error", "Business accounts need a shop name")