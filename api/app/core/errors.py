from collections.abc import Mapping
from datetime import UTC, datetime
from enum import Enum
from typing import Any

from fastapi import HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.core.logging import logger, request_id_ctx


class ErrorCode(str, Enum):
    VALIDATION_ERROR = "VALIDATION_ERROR"
    NOT_FOUND = "NOT_FOUND"
    UNAUTHORIZED = "UNAUTHORIZED"
    FORBIDDEN = "FORBIDDEN"
    RATE_LIMITED = "RATE_LIMITED"
    LLM_UNAVAILABLE = "LLM_UNAVAILABLE"
    LLM_INVALID_OUTPUT = "LLM_INVALID_OUTPUT"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    NO_ROUTE_FOUND = "NO_ROUTE_FOUND"
    AGENT_TIMEOUT = "AGENT_TIMEOUT"
    AGENT_FAILED = "AGENT_FAILED"
    DB_UNAVAILABLE = "DB_UNAVAILABLE"
    INTERNAL_ERROR = "INTERNAL_ERROR"


class ErrorDetail(BaseModel):
    code: str
    message: str
    details: dict[str, Any] | None = None
    request_id: str | None = None
    timestamp: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())


class ErrorEnvelope(BaseModel):
    error: ErrorDetail


class AppException(HTTPException):
    def __init__(
        self,
        status_code: int,
        code: ErrorCode | str,
        message: str,
        details: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(status_code=status_code, detail=message, headers=headers)
        self.code = code.value if isinstance(code, ErrorCode) else code
        self.message = message
        self.details = details or {}


def create_error_response(
    status_code: int,
    code: str,
    message: str,
    details: dict[str, Any] | None = None,
    request_id: str | None = None,
    headers: Mapping[str, str] | None = None,
) -> JSONResponse:
    req_id = request_id or request_id_ctx.get() or None
    body = ErrorEnvelope(
        error=ErrorDetail(
            code=code,
            message=message,
            details=details,
            request_id=req_id,
        )
    ).model_dump()

    response_headers = dict(headers) if headers else {}
    if req_id:
        response_headers["X-Request-ID"] = req_id

    return JSONResponse(status_code=status_code, content=body, headers=response_headers)


async def app_exception_handler(request: Request, exc: AppException) -> JSONResponse:
    logger.warning("app_exception", code=exc.code, message=exc.message, details=exc.details)
    return create_error_response(
        status_code=exc.status_code,
        code=exc.code,
        message=exc.message,
        details=exc.details,
        headers=exc.headers,
    )


async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    logger.warning("validation_error", errors=exc.errors())
    return create_error_response(
        status_code=status.HTTP_400_BAD_REQUEST,
        code=ErrorCode.VALIDATION_ERROR.value,
        message="Request validation failed",
        details={"validation_errors": exc.errors()},
    )


async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.error("unhandled_exception", exc_info=exc)
    return create_error_response(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        code=ErrorCode.INTERNAL_ERROR.value,
        message="An internal server error occurred",
    )
