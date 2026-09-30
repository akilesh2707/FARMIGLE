"""Structured API errors.

One exception hierarchy + one response shape for the whole service:

    {"error": "IMAGE_QUALITY_FAILED",
     "message": "The image is too blurry. Please retake the photo.",
     "details": {...}}

Internal exception text, stack traces and credentials never reach the client:
``ApiError.__str__`` is safe, and unexpected exceptions are logged server-side
and replaced by a generic ``INTERNAL_ERROR`` body by the handler installed in
``backend.main``.
"""

from __future__ import annotations

from typing import Any

from fastapi import status


class ErrorCode:
    """Stable machine-readable error codes."""

    # 400
    VALIDATION_ERROR = "VALIDATION_ERROR"
    INVALID_BOUNDARY = "INVALID_BOUNDARY"
    INVALID_SOURCE = "INVALID_SOURCE"
    INVALID_AUDIO = "INVALID_AUDIO"
    # 401 / 403
    UNAUTHENTICATED = "UNAUTHENTICATED"
    INVALID_TOKEN = "INVALID_TOKEN"
    FORBIDDEN = "FORBIDDEN"
    # 404
    NOT_FOUND = "NOT_FOUND"
    FARM_NOT_FOUND = "FARM_NOT_FOUND"
    ZONE_NOT_FOUND = "ZONE_NOT_FOUND"
    OBSERVATION_NOT_FOUND = "OBSERVATION_NOT_FOUND"
    # 409
    CONFLICT = "CONFLICT"
    # 413 / 415
    PAYLOAD_TOO_LARGE = "PAYLOAD_TOO_LARGE"
    UNSUPPORTED_MEDIA_TYPE = "UNSUPPORTED_MEDIA_TYPE"
    # 422 - image pipeline
    IMAGE_QUALITY_FAILED = "IMAGE_QUALITY_FAILED"
    IMAGE_UNREADABLE = "IMAGE_UNREADABLE"
    # 429 / 5xx
    RATE_LIMITED = "RATE_LIMITED"
    PROVIDER_ERROR = "PROVIDER_ERROR"
    PROVIDER_UNAVAILABLE = "PROVIDER_UNAVAILABLE"
    INTERNAL_ERROR = "INTERNAL_ERROR"


class ApiError(Exception):
    """Base class for every error the API deliberately returns."""

    code: str = ErrorCode.INTERNAL_ERROR
    http_status: int = status.HTTP_500_INTERNAL_SERVER_ERROR

    def __init__(
        self,
        message: str,
        *,
        code: str | None = None,
        http_status: int | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        if code is not None:
            self.code = code
        if http_status is not None:
            self.http_status = http_status
        self.details: dict[str, Any] = details or {}

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"error": self.code, "message": self.message}
        if self.details:
            payload["details"] = self.details
        return payload

    def __str__(self) -> str:  # pragma: no cover - trivial
        return f"{self.code}: {self.message}"


class BadRequestError(ApiError):
    code = ErrorCode.VALIDATION_ERROR
    http_status = status.HTTP_400_BAD_REQUEST


class InvalidBoundaryError(BadRequestError):
    """Boundary validation failure. ``reason`` is a stable machine code."""

    code = ErrorCode.INVALID_BOUNDARY

    def __init__(
        self,
        message: str,
        *,
        reason: str = "invalid_boundary",
        details: dict[str, Any] | None = None,
    ) -> None:
        merged = {"reason": reason}
        if details:
            merged.update(details)
        super().__init__(message, details=merged)
        self.reason = reason


class InvalidSourceError(BadRequestError):
    code = ErrorCode.INVALID_SOURCE


class InvalidAudioError(BadRequestError):
    code = ErrorCode.INVALID_AUDIO


class UnauthenticatedError(ApiError):
    code = ErrorCode.UNAUTHENTICATED
    http_status = status.HTTP_401_UNAUTHORIZED


class InvalidTokenError(UnauthenticatedError):
    code = ErrorCode.INVALID_TOKEN


class ForbiddenError(ApiError):
    code = ErrorCode.FORBIDDEN
    http_status = status.HTTP_403_FORBIDDEN


class NotFoundError(ApiError):
    code = ErrorCode.NOT_FOUND
    http_status = status.HTTP_404_NOT_FOUND


class FarmNotFoundError(NotFoundError):
    code = ErrorCode.FARM_NOT_FOUND


class ZoneNotFoundError(NotFoundError):
    code = ErrorCode.ZONE_NOT_FOUND


class ObservationNotFoundError(NotFoundError):
    code = ErrorCode.OBSERVATION_NOT_FOUND


class ConflictError(ApiError):
    code = ErrorCode.CONFLICT
    http_status = status.HTTP_409_CONFLICT


class PayloadTooLargeError(ApiError):
    code = ErrorCode.PAYLOAD_TOO_LARGE
    # 413. Written as a literal so the module does not depend on which
    # starlette spelling of the constant is present.
    http_status = 413


class UnsupportedMediaTypeError(ApiError):
    code = ErrorCode.UNSUPPORTED_MEDIA_TYPE
    http_status = 415


class ImageQualityError(ApiError):
    """Image failed the Section 8.3 quality gate - farmer should retake.

    Returned as HTTP 422 so a client can distinguish "your photo is unusable,
    retake it" from "your request was malformed".
    """

    code = ErrorCode.IMAGE_QUALITY_FAILED
    http_status = 422

    def __init__(
        self,
        message: str,
        *,
        reason: str,
        remedy: str,
        metrics: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            message,
            details={
                "reason": reason,
                "remedy": remedy,
                "retake_required": True,
                "metrics": metrics or {},
            },
        )
        self.reason = reason
        self.remedy = remedy


class ImageUnreadableError(ApiError):
    code = ErrorCode.IMAGE_UNREADABLE
    http_status = 422


class ProviderError(ApiError):
    """An external provider (Gemini, speech, weather) failed.

    The provider's own message is deliberately NOT forwarded.
    """

    code = ErrorCode.PROVIDER_ERROR
    http_status = status.HTTP_502_BAD_GATEWAY


class ProviderUnavailableError(ProviderError):
    code = ErrorCode.PROVIDER_UNAVAILABLE
    http_status = status.HTTP_503_SERVICE_UNAVAILABLE
