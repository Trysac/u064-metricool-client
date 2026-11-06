"""Metricool client core: authenticated requests, retries and pagination."""

from __future__ import annotations

import json
import logging
import re
import time
from collections.abc import Callable, Iterator, Mapping
from datetime import date, datetime
from urllib.parse import urlencode, urlsplit

from ._endpoints import (
    LIST_COMMENTS,
    SCHEDULE_POST,
    comments_query,
    parse_comments_page,
    parse_post_id,
    schedule_payload,
    schedule_query,
)
from ._errors import MetricoolError
from ._models import KNOWN_NETWORKS, Comment, PostDraft
from ._transport import HttpResponse, Transport

_LOG = logging.getLogger(__name__)
_LOG.addHandler(logging.NullHandler())

_DEFAULT_BASE_URL = "https://app.metricool.com/api"
_MAX_BACKOFF_SECONDS = 60
_TOKEN_RE = re.compile(r"[\x20-\x7e]{1,4096}")
_ID_RE = re.compile(r"[\x21-\x7e]{1,128}")
_PATH_RE = re.compile(r"/[A-Za-z0-9._~!$&'()*+,;=:@%/-]{0,511}")
_UNSAFE_URL_RE = re.compile(r"[\x00-\x20\x7f]")


def _invalid(message: str) -> MetricoolError:
    return MetricoolError("invalid_input", message)


def _check_int(name: str, value: object, low: int, high: int) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
        raise _invalid(f"{name} must be an integer between {low} and {high}")


def _check_base_url(value: object) -> str:
    if not isinstance(value, str) or len(value) > 2048 or _UNSAFE_URL_RE.search(value):
        raise _invalid("base_url must be a valid https URL")
    try:
        parts = urlsplit(value)
        host = parts.hostname
    except ValueError:
        raise _invalid("base_url must be a valid https URL") from None
    bad = "@" in parts.netloc or "?" in value or "#" in value
    if parts.scheme != "https" or not host or bad:
        raise _invalid("base_url must be an https URL without credentials, query or fragment")
    return value.rstrip("/")


def _check_endpoints(endpoints: object) -> dict[str, str]:
    if not isinstance(endpoints, Mapping):
        raise _invalid("endpoints must be a mapping")
    paths: dict[str, str] = {}
    for key in (SCHEDULE_POST, LIST_COMMENTS):
        path = endpoints.get(key)
        if (
            not isinstance(path, str)
            or _PATH_RE.fullmatch(path) is None
            or path.startswith("//")
            or ".." in path.split("/")
        ):
            raise _invalid(f"endpoints[{key!r}] must be a path relative to base_url")
        paths[key] = path
    return paths


def _parse_retry_after(value: object) -> int | None:
    text = value.strip() if isinstance(value, str) else ""
    if 1 <= len(text) <= 9 and text.isascii() and text.isdigit():
        return int(text)
    return None


def _retry_delay(headers: Mapping[str, str], attempt: int) -> float:
    backoff = float(min(2 ** (attempt - 1), _MAX_BACKOFF_SECONDS))
    for name, value in headers.items():
        if name.lower() == "retry-after":
            seconds = _parse_retry_after(value)
            return backoff if seconds is None else min(seconds, _MAX_BACKOFF_SECONDS)
    return backoff


def _parse_json(body: bytes) -> object:
    try:
        data: object = json.loads(body)
    except (ValueError, RecursionError):
        raise MetricoolError("invalid_response", "response body is not valid JSON") from None
    return data


class MetricoolClient:
    """Client for the Metricool API.

    Args:
        user_token: API token, sent only in the ``X-Mc-Auth`` header.
        user_id: Sent as the ``userId`` query parameter.
        blog_id: Sent as the ``blogId`` query parameter.
        transport: Performs the HTTP exchange.
        endpoints: Paths relative to ``base_url`` for the keys ``schedule_post``
            and ``list_comments``. Required: no default is bundled.
        base_url: Must be ``https``.
        sleep: Called with the number of seconds to wait before a retry.
        max_retries: Retries after a 429 (any method) or a 503 (GET only).
        max_pages: Largest number of non-empty comment pages accepted.
        max_response_bytes: Largest accepted response body.
        on_event: Called after every attempt with the keys ``method``, ``path``,
            ``status`` (0 when the transport failed) and ``attempt`` only.

    Raises:
        MetricoolError: ``invalid_input`` when an argument is invalid.
    """

    def __init__(
        self,
        user_token: str,
        user_id: str,
        blog_id: str,
        *,
        transport: Transport,
        endpoints: Mapping[str, str],
        base_url: str = _DEFAULT_BASE_URL,
        sleep: Callable[[float], None] = time.sleep,
        max_retries: int = 3,
        max_pages: int = 1000,
        max_response_bytes: int = 10_485_760,
        on_event: Callable[[Mapping[str, str | int]], None] | None = None,
    ) -> None:
        if not isinstance(user_token, str) or not _TOKEN_RE.fullmatch(user_token):
            raise _invalid("user_token must be 1-4096 printable ASCII characters")
        if not isinstance(user_id, str) or not _ID_RE.fullmatch(user_id):
            raise _invalid("user_id must be 1-128 printable ASCII characters without spaces")
        if not isinstance(blog_id, str) or not _ID_RE.fullmatch(blog_id):
            raise _invalid("blog_id must be 1-128 printable ASCII characters without spaces")
        if not callable(getattr(transport, "send", None)):
            raise _invalid("transport must provide a send method")
        if not callable(sleep):
            raise _invalid("sleep must be callable")
        if on_event is not None and not callable(on_event):
            raise _invalid("on_event must be callable")
        _check_int("max_retries", max_retries, 0, 10)
        _check_int("max_pages", max_pages, 1, 100_000)
        _check_int("max_response_bytes", max_response_bytes, 1, 1_073_741_824)
        self._token = user_token
        self._user_id = user_id
        self._blog_id = blog_id
        self._transport = transport
        self._paths = _check_endpoints(endpoints)
        self._base_url = _check_base_url(base_url)
        self._sleep = sleep
        self._max_retries = max_retries
        self._max_pages = max_pages
        self._max_response_bytes = max_response_bytes
        self._on_event = on_event

    def __repr__(self) -> str:
        return f"MetricoolClient(base_url={self._base_url!r})"

    def schedule_post(self, post: PostDraft) -> str:
        """Schedule ``post`` and return the id of the created post.

        Raises:
            MetricoolError: on invalid input, API errors, rate limiting, oversized
                or malformed responses. A 503 answer is never retried here because
                a POST is not idempotent.
        """
        if not isinstance(post, PostDraft):
            raise _invalid("post must be a PostDraft")
        query = schedule_query(self._user_id, self._blog_id)
        data = self._request("POST", SCHEDULE_POST, query, schedule_payload(post))
        return parse_post_id(data)

    def list_comments(
        self,
        network: str,
        start: date,
        end: date,
        *,
        page_size: int = 50,
    ) -> Iterator[Comment]:
        """Return an iterator over the comments of ``network`` from ``start`` to ``end``.

        Arguments are validated immediately; pages are fetched lazily until an
        empty page. More than ``max_pages`` non-empty pages raise
        ``invalid_response``.

        Raises:
            MetricoolError: ``invalid_input`` when an argument is invalid or
                ``end`` is before ``start``; other codes while iterating.
        """
        if not isinstance(network, str) or network not in KNOWN_NETWORKS:
            raise _invalid("network is not a known network")
        for value in (start, end):
            if not isinstance(value, date) or isinstance(value, datetime):
                raise _invalid("start and end must be date objects")
        if end < start:
            raise _invalid("end must not be before start")
        _check_int("page_size", page_size, 1, 500)
        return self._iter_comments(network, start, end, page_size)

    def _iter_comments(
        self,
        network: str,
        start: date,
        end: date,
        page_size: int,
    ) -> Iterator[Comment]:
        page = 1
        while True:
            query = comments_query(
                self._user_id,
                self._blog_id,
                network,
                start,
                end,
                page,
                page_size,
            )
            data = self._request("GET", LIST_COMMENTS, query, None)
            comments = parse_comments_page(data, network)
            if not comments:
                return
            if page > self._max_pages:
                raise MetricoolError("invalid_response", "more pages than max_pages")
            yield from comments
            page += 1

    def _emit(self, method: str, path: str, status: int, attempt: int) -> None:
        _LOG.debug("request %s %s -> %d (attempt %d)", method, path, status, attempt)
        if self._on_event is None:
            return
        event: dict[str, str | int] = {
            "method": method,
            "path": path,
            "status": status,
            "attempt": attempt,
        }
        try:
            self._on_event(event)
        except Exception as exc:
            _LOG.warning("on_event callback raised %s", type(exc).__name__)

    def _send(
        self,
        method: str,
        path: str,
        url: str,
        headers: Mapping[str, str],
        body: bytes | None,
        attempt: int,
    ) -> HttpResponse:
        try:
            response = self._transport.send(method, url, headers, body)
        except OSError as exc:
            self._emit(method, path, 0, attempt)
            raise MetricoolError("api_error", f"transport failure: {type(exc).__name__}") from None
        self._emit(method, path, response.status, attempt)
        return response

    def _request(
        self,
        method: str,
        endpoint: str,
        query: Mapping[str, str],
        payload: Mapping[str, object] | None,
    ) -> object:
        path = self._paths[endpoint]
        url = f"{self._base_url}{path}?{urlencode(query)}"
        headers = {"X-Mc-Auth": self._token, "Accept": "application/json"}
        body: bytes | None = None
        if payload is not None:
            body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
            headers["Content-Type"] = "application/json"
        attempt = 0
        while True:
            attempt += 1
            response = self._send(method, path, url, headers, body, attempt)
            status = response.status
            if len(response.body) > self._max_response_bytes:
                raise MetricoolError("too_large", "response exceeds the size limit", status)
            retryable = status == 429 or (status == 503 and method == "GET")
            if retryable and attempt <= self._max_retries:
                self._sleep(_retry_delay(response.headers, attempt))
                continue
            if 200 <= status < 300:
                return _parse_json(response.body)
            if status == 429:
                raise MetricoolError("rate_limited", "rate limit exceeded after retries", status)
            raise MetricoolError("api_error", f"Metricool API returned HTTP {status}", status)
