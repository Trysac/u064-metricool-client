"""HTTP transport abstraction and a stdlib adapter."""

from __future__ import annotations

import math
import urllib.error
import urllib.request
from collections.abc import Mapping
from http.client import HTTPMessage
from typing import IO, NamedTuple, Protocol
from urllib.parse import urlsplit

from ._errors import MetricoolError

_DEFAULT_MAX_READ_BYTES = 10_485_761


class HttpResponse(NamedTuple):
    """A complete HTTP response: status code, headers and raw body."""

    status: int
    headers: dict[str, str]
    body: bytes


class Transport(Protocol):
    """Anything able to perform one HTTP exchange."""

    def send(
        self,
        method: str,
        url: str,
        headers: Mapping[str, str],
        body: bytes | None,
    ) -> HttpResponse:
        """Send one request and return the response, whatever its status code.

        Network failures should raise ``OSError``.
        """


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Refuse every redirect so custom headers never reach another host."""

    def redirect_request(
        self,
        req: urllib.request.Request,
        fp: IO[bytes],
        code: int,
        msg: str,
        headers: HTTPMessage,
        newurl: str,
    ) -> urllib.request.Request | None:
        return None


def _build_opener() -> urllib.request.OpenerDirector:
    opener = urllib.request.OpenerDirector()
    opener.add_handler(urllib.request.HTTPSHandler())
    opener.add_handler(_NoRedirectHandler())
    opener.add_handler(urllib.request.HTTPDefaultErrorHandler())
    opener.add_handler(urllib.request.HTTPErrorProcessor())
    return opener


def _require_https(url: str) -> None:
    try:
        parts = urlsplit(url)
        valid = parts.scheme == "https" and bool(parts.hostname)
    except ValueError:
        valid = False
    if not valid:
        raise MetricoolError("invalid_input", "only https URLs are accepted")


class UrllibTransport:
    """Thin stdlib transport.

    It accepts only ``https`` URLs and never follows redirects (a 3xx answer is
    returned as a normal response), because urllib would copy custom headers such
    as ``X-Mc-Auth`` to the redirect target. Non-2xx answers are returned, not
    raised. At most ``max_read_bytes`` of a body are read.
    """

    def __init__(
        self,
        timeout: float = 30.0,
        *,
        max_read_bytes: int = _DEFAULT_MAX_READ_BYTES,
    ) -> None:
        timeout_ok = isinstance(timeout, int | float) and not isinstance(timeout, bool)
        if not timeout_ok or not math.isfinite(timeout) or timeout <= 0:
            raise MetricoolError("invalid_input", "timeout must be a positive number")
        if isinstance(max_read_bytes, bool) or not isinstance(max_read_bytes, int):
            raise MetricoolError("invalid_input", "max_read_bytes must be a positive integer")
        if max_read_bytes < 1:
            raise MetricoolError("invalid_input", "max_read_bytes must be a positive integer")
        self._timeout = float(timeout)
        self._max_read_bytes = max_read_bytes
        self._opener = _build_opener()

    def send(
        self,
        method: str,
        url: str,
        headers: Mapping[str, str],
        body: bytes | None,
    ) -> HttpResponse:
        """Send one request over HTTPS and return the response."""
        _require_https(url)
        request = urllib.request.Request(url, data=body, headers=dict(headers), method=method)  # noqa: S310
        try:
            with self._opener.open(request, timeout=self._timeout) as response:
                data = response.read(self._max_read_bytes)
                return HttpResponse(response.status, dict(response.headers.items()), data)
        except urllib.error.HTTPError as exc:
            try:
                data = exc.read(self._max_read_bytes)
                return HttpResponse(exc.code, dict(exc.headers.items()), data)
            finally:
                exc.close()
