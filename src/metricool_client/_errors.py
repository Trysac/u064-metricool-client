"""Typed error raised by every failure in the library."""

from __future__ import annotations

from typing import Literal

ErrorCode = Literal["api_error", "rate_limited", "invalid_input", "invalid_response", "too_large"]

_MAX_MESSAGE_CHARS = 200


class MetricoolError(Exception):
    """Base error of the library.

    Attributes:
        code: Stable machine-readable error code.
        status: HTTP status of the response that caused the error, if any.

    Messages are capped at 200 characters and never contain credentials,
    response bodies or request URLs.
    """

    def __init__(self, code: ErrorCode, message: str, status: int | None = None) -> None:
        super().__init__(message[:_MAX_MESSAGE_CHARS])
        self.code: ErrorCode = code
        self.status: int | None = status

    def __reduce__(self) -> tuple[type[MetricoolError], tuple[ErrorCode, str, int | None]]:
        return (type(self), (self.code, str(self), self.status))
