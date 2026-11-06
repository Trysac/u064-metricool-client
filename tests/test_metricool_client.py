"""Behavioural tests for metricool_client using fake transports only."""

from __future__ import annotations

import copy
import csv
import dataclasses
import io
import json
import logging
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta, timezone
from email.message import Message
from typing import Any, NamedTuple
from urllib.parse import parse_qs, urlsplit

import pytest

import metricool_client
import metricool_client._transport as transport_module
from metricool_client import (
    Comment,
    HttpResponse,
    MetricoolClient,
    MetricoolError,
    PostDraft,
    UrllibTransport,
    export_comments_csv,
)

SENTINEL = "zzcredzz-0001"
ENDPOINTS = {"schedule_post": "/v1/posts", "list_comments": "/v1/comments"}
AWARE = datetime(2026, 1, 2, 9, 30, tzinfo=timezone(timedelta(hours=-5)))
START = date(2026, 1, 1)
END = date(2026, 1, 31)


class Call(NamedTuple):
    method: str
    url: str
    headers: dict[str, str]
    body: bytes | None


class FakeTransport:
    """Scripted transport: returns or raises the queued items in order."""

    def __init__(self, *responses: HttpResponse | Exception) -> None:
        self._responses = list(responses)
        self.calls: list[Call] = []

    def send(self, method: str, url: str, headers: Any, body: bytes | None) -> HttpResponse:
        self.calls.append(Call(method, url, dict(headers), body))
        item = self._responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


class Harness:
    def __init__(self, *responses: HttpResponse | Exception, **options: Any) -> None:
        self.transport = FakeTransport(*responses)
        self.sleeps: list[float] = []
        self.events: list[dict[str, Any]] = []
        self.client = MetricoolClient(
            SENTINEL,
            "42",
            "7",
            transport=self.transport,
            endpoints=ENDPOINTS,
            sleep=self.sleeps.append,
            on_event=lambda event: self.events.append(dict(event)),
            **options,
        )


def reply(payload: Any, status: int = 200, hdrs: Any = None) -> HttpResponse:
    return HttpResponse(status, hdrs or {}, json.dumps(payload).encode("utf-8"))


def draft(**over: Any) -> PostDraft:
    fields: dict[str, Any] = {
        "text": "hello world",
        "networks": ("facebook", "instagram"),
        "publish_at": AWARE,
        "media_urls": ("https://cdn.example.com/a.png",),
    }
    fields.update(over)
    return PostDraft(**fields)


def item(n: int, **over: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "id": f"c{n}",
        "author": "Ana",
        "text": "hi",
        "createdAt": "2026-01-02T09:30:00-05:00",
        "postId": "p1",
    }
    data.update(over)
    return data


def page(*items: Any) -> HttpResponse:
    return reply({"comments": list(items)})


def query(call: Call) -> dict[str, list[str]]:
    return parse_qs(urlsplit(call.url).query)


def build(**over: Any) -> MetricoolClient:
    args: dict[str, Any] = {
        "user_token": SENTINEL,
        "user_id": "42",
        "blog_id": "7",
        "transport": FakeTransport(),
        "endpoints": dict(ENDPOINTS),
    }
    args.update(over)
    return MetricoolClient(**args)


# ---------------------------------------------------------------- package


def test_public_api_and_version() -> None:
    assert metricool_client.__version__ == "0.1.0"
    for name in metricool_client.__all__:
        assert hasattr(metricool_client, name)


def test_library_only_installs_null_handlers() -> None:
    package_logger = logging.getLogger("metricool_client")
    client_logger = logging.getLogger("metricool_client._client")
    assert any(isinstance(h, logging.NullHandler) for h in package_logger.handlers)
    assert any(isinstance(h, logging.NullHandler) for h in client_logger.handlers)
    assert all(not isinstance(h, logging.StreamHandler) for h in client_logger.handlers)


# ----------------------------------------------------------------- errors


def test_error_message_is_capped_and_survives_copy() -> None:
    err = MetricoolError("api_error", "x" * 500, 500)
    assert len(str(err)) == 200
    clone = copy.deepcopy(err)
    assert (clone.code, clone.status, str(clone)) == ("api_error", 500, str(err))
    assert MetricoolError("too_large", "m").status is None


# ------------------------------------------------------------- schedule


def test_schedule_post_sends_token_only_in_header() -> None:
    h = Harness(reply({"id": "post-123"}))
    assert h.client.schedule_post(draft()) == "post-123"
    call = h.transport.calls[0]
    parts = urlsplit(call.url)
    assert call.method == "POST"
    assert parts.scheme == "https"
    assert parts.netloc == "app.metricool.com"
    assert parts.path == "/api/v1/posts"
    assert parse_qs(parts.query) == {"userId": ["42"], "blogId": ["7"]}
    assert call.headers["X-Mc-Auth"] == SENTINEL
    assert call.headers["Content-Type"] == "application/json"
    assert SENTINEL not in call.url
    sent = json.loads(call.body or b"")
    assert sent["text"] == "hello world"
    assert sent["networks"] == ["facebook", "instagram"]
    assert sent["media"] == ["https://cdn.example.com/a.png"]
    assert SENTINEL not in (call.body or b"").decode()


def test_publish_at_is_serialised_with_its_offset() -> None:
    h = Harness(reply({"id": "a"}), reply({"id": "b"}))
    h.client.schedule_post(draft())
    when = datetime(2026, 1, 2, 9, 30, 15, 999999, tzinfo=timezone.utc)
    h.client.schedule_post(draft(publish_at=when))
    first = json.loads(h.transport.calls[0].body or b"")
    second = json.loads(h.transport.calls[1].body or b"")
    assert first["publishAt"] == "2026-01-02T09:30:00-05:00"
    assert second["publishAt"] == "2026-01-02T09:30:15+00:00"


def test_naive_publish_at_raises_invalid_input() -> None:
    with pytest.raises(MetricoolError) as info:
        draft(publish_at=datetime(2026, 1, 2, 9, 30))
    assert info.value.code == "invalid_input"


BAD_DRAFTS: list[dict[str, Any]] = [
    {"text": ""},
    {"text": "x" * 5001},
    {"text": 5},
    {"networks": ()},
    {"networks": ["facebook"]},
    {"networks": ("myspace",)},
    {"networks": ("facebook", "facebook")},
    {"networks": (5,)},
    {"publish_at": "2026-01-02"},
    {"media_urls": ("http://cdn.example.com/a.png",)},
    {"media_urls": ["https://cdn.example.com/a.png"]},
    {"media_urls": ("https://cdn.example.com/a b.png",)},
    {"media_urls": ("https://user@cdn.example.com/a.png",)},
    {"media_urls": ("https:///a.png",)},
    {"media_urls": ("https://[::1/a.png",)},
    {"media_urls": (5,)},
    {"media_urls": ("",)},
    {"media_urls": ("https://cdn.example.com/" + "a" * 2048,)},
    {"media_urls": ("https://cdn.example.com/a.png",) * 11},
]


@pytest.mark.parametrize("over", BAD_DRAFTS)
def test_invalid_drafts_are_rejected(over: dict[str, Any]) -> None:
    with pytest.raises(MetricoolError) as info:
        draft(**over)
    assert info.value.code == "invalid_input"


def test_draft_boundaries_are_accepted() -> None:
    media = ("https://cdn.example.com/a.png",) * 10
    ok = draft(text="x" * 5000, media_urls=media)
    assert len(ok.text) == 5000
    assert len(ok.media_urls) == 10
    assert draft(media_urls=()).media_urls == ()
    with pytest.raises(dataclasses.FrozenInstanceError):
        ok.text = "changed"  # type: ignore[misc]


def test_schedule_post_rejects_non_drafts_and_tampered_drafts() -> None:
    h = Harness()
    with pytest.raises(MetricoolError) as info:
        h.client.schedule_post("hello")  # type: ignore[arg-type]
    assert info.value.code == "invalid_input"
    tampered = draft()
    object.__setattr__(tampered, "text", "")
    with pytest.raises(MetricoolError) as info2:
        h.client.schedule_post(tampered)
    assert info2.value.code == "invalid_input"
    assert h.transport.calls == []


def test_schedule_post_503_is_sent_exactly_once() -> None:
    h = Harness(reply({}, 503), reply({"id": "x"}))
    with pytest.raises(MetricoolError) as info:
        h.client.schedule_post(draft())
    assert info.value.code == "api_error"
    assert info.value.status == 503
    assert len(h.transport.calls) == 1
    assert h.sleeps == []


def test_schedule_post_429_is_retried() -> None:
    h = Harness(reply({}, 429), reply({"id": "x"}))
    assert h.client.schedule_post(draft()) == "x"
    assert h.sleeps == [1]
    assert len(h.transport.calls) == 2


def test_schedule_response_with_integer_id() -> None:
    h = Harness(reply({"id": 5}))
    assert h.client.schedule_post(draft()) == "5"


@pytest.mark.parametrize(
    "payload",
    [[], {}, {"id": True}, {"id": ""}, {"id": None}, {"id": "x" * 201}, {"id": ["a"]}],
)
def test_schedule_response_shape_is_validated(payload: Any) -> None:
    h = Harness(reply(payload))
    with pytest.raises(MetricoolError) as info:
        h.client.schedule_post(draft())
    assert info.value.code == "invalid_response"


# -------------------------------------------------------------- comments


def test_list_comments_follows_pages_until_an_empty_page() -> None:
    h = Harness(page(item(1), item(2)), page(item(3)), page())
    comments = list(h.client.list_comments("facebook", START, END))
    assert [c.id for c in comments] == ["c1", "c2", "c3"]
    first = comments[0]
    assert (first.network, first.author, first.text, first.post_id) == (
        "facebook",
        "Ana",
        "hi",
        "p1",
    )
    assert first.created_at == AWARE
    calls = h.transport.calls
    assert [query(c)["page"] for c in calls] == [["1"], ["2"], ["3"]]
    assert query(calls[0])["network"] == ["facebook"]
    assert query(calls[0])["start"] == ["2026-01-01"]
    assert query(calls[0])["end"] == ["2026-01-31"]
    assert query(calls[0])["pageSize"] == ["50"]
    assert query(calls[0])["userId"] == ["42"]
    assert calls[0].method == "GET"
    assert calls[0].body is None
    assert calls[0].headers["X-Mc-Auth"] == SENTINEL
    assert "Content-Type" not in calls[0].headers
    assert all(SENTINEL not in c.url for c in calls)


def test_list_comments_is_lazy_and_honours_page_size() -> None:
    h = Harness(page())
    iterator = h.client.list_comments("facebook", START, START, page_size=7)
    assert h.transport.calls == []
    assert list(iterator) == []
    assert query(h.transport.calls[0])["pageSize"] == ["7"]


def test_max_pages_rejects_a_third_non_empty_page() -> None:
    h = Harness(page(item(1)), page(item(2)), page(item(3)), max_pages=2)
    with pytest.raises(MetricoolError) as info:
        list(h.client.list_comments("facebook", START, END))
    assert info.value.code == "invalid_response"
    assert len(h.transport.calls) == 3


def test_max_pages_allows_exactly_that_many_pages() -> None:
    h = Harness(page(item(1)), page(item(2)), page(), max_pages=2)
    assert len(list(h.client.list_comments("facebook", START, END))) == 2


BAD_LIST_ARGS: list[tuple[Any, Any, Any, Any]] = [
    ("myspace", START, END, 50),
    (5, START, END, 50),
    ("facebook", "2026-01-01", END, 50),
    ("facebook", START, datetime(2026, 1, 31), 50),
    ("facebook", datetime(2026, 1, 1), END, 50),
    ("facebook", END, START, 50),
    ("facebook", START, END, 0),
    ("facebook", START, END, 501),
    ("facebook", START, END, True),
]


@pytest.mark.parametrize(("network", "start", "end", "size"), BAD_LIST_ARGS)
def test_list_comments_validates_arguments_eagerly(
    network: Any,
    start: Any,
    end: Any,
    size: Any,
) -> None:
    h = Harness()
    with pytest.raises(MetricoolError) as info:
        h.client.list_comments(network, start, end, page_size=size)
    assert info.value.code == "invalid_input"
    assert h.transport.calls == []


def test_comment_fields_are_mapped_with_defaults() -> None:
    zulu = item(1, createdAt="2026-01-02T14:30:00Z")
    sparse = {"id": 5, "createdAt": "2026-01-02T14:30:00+00:00", "network": "instagram"}
    h = Harness(page(zulu, sparse), page())
    first, second = h.client.list_comments("facebook", START, END)
    assert first.created_at == AWARE
    assert first.created_at.utcoffset() == timedelta(0)
    assert (second.id, second.network, second.author, second.text, second.post_id) == (
        "5",
        "instagram",
        "",
        "",
        "",
    )


BAD_COMMENT_PAGES: list[Any] = [
    [],
    {},
    {"comments": "x"},
    {"comments": ["x"]},
    {"comments": [{"text": "no id"}]},
    {"comments": [item(1, id=True)]},
    {"comments": [item(1, id="")]},
    {"comments": [item(1, createdAt="yesterday")]},
    {"comments": [item(1, createdAt="2026-01-02T09:30:00")]},
    {"comments": [item(1, createdAt=5)]},
    {"comments": [item(1, createdAt="")]},
    {"comments": [item(1, createdAt="2" * 65)]},
    {"comments": [item(1, author={"x": 1})]},
    {"comments": [item(1, text=True)]},
    {"comments": [{}] * 10_001},
]


@pytest.mark.parametrize("payload", BAD_COMMENT_PAGES)
def test_comment_page_shape_is_validated(payload: Any) -> None:
    h = Harness(reply(payload))
    with pytest.raises(MetricoolError) as info:
        list(h.client.list_comments("facebook", START, END))
    assert info.value.code == "invalid_response"


# ------------------------------------------------------------- retries


def test_429_is_retried_after_1_2_4_then_rate_limited() -> None:
    h = Harness(*[reply({}, 429)] * 4)
    with pytest.raises(MetricoolError) as info:
        h.client.schedule_post(draft())
    assert info.value.code == "rate_limited"
    assert info.value.status == 429
    assert h.sleeps == [1, 2, 4]
    assert len(h.transport.calls) == 4
    assert SENTINEL not in str(info.value)


def test_backoff_is_capped_at_60_seconds() -> None:
    h = Harness(*[reply({}, 429)] * 9, max_retries=8)
    with pytest.raises(MetricoolError):
        h.client.schedule_post(draft())
    assert h.sleeps == [1, 2, 4, 8, 16, 32, 60, 60]


def test_zero_retries_fail_immediately() -> None:
    h = Harness(reply({}, 429), max_retries=0)
    with pytest.raises(MetricoolError) as info:
        h.client.schedule_post(draft())
    assert info.value.code == "rate_limited"
    assert h.sleeps == []


RETRY_AFTER_CASES = [
    ("7", 7),
    ("120", 60),
    ("2.5", 1),
    ("Wed, 21 Oct 2015 07:28:00 GMT", 1),
    ("-3", 1),
    ("+3", 1),
    ("", 1),
    (" 5 ", 5),
    ("0", 0),
    ("9" * 12, 1),
]


@pytest.mark.parametrize(("value", "expected"), RETRY_AFTER_CASES)
def test_retry_after_is_integer_seconds_only(value: str, expected: int) -> None:
    h = Harness(reply({}, 429, {"Retry-After": value}), reply({"id": "ok"}))
    assert h.client.schedule_post(draft()) == "ok"
    assert h.sleeps == [expected]


def test_retry_after_header_name_is_case_insensitive() -> None:
    h = Harness(reply({}, 429, {"retry-after": "7"}), reply({"id": "ok"}))
    h.client.schedule_post(draft())
    assert h.sleeps == [7]


def test_get_503_is_retried_then_succeeds() -> None:
    h = Harness(reply({}, 503), page())
    assert list(h.client.list_comments("facebook", START, END)) == []
    assert h.sleeps == [1]


def test_get_503_gives_up_with_api_error() -> None:
    h = Harness(reply({}, 503), reply({}, 503), max_retries=1)
    with pytest.raises(MetricoolError) as info:
        list(h.client.list_comments("facebook", START, END))
    assert (info.value.code, info.value.status) == ("api_error", 503)
    assert h.sleeps == [1]


# ---------------------------------------------------------- error paths


@pytest.mark.parametrize("status", [301, 400, 401, 404, 500, 503])
def test_non_2xx_raises_api_error_without_leaking(status: int) -> None:
    body = (SENTINEL + "x" * 500).encode("utf-8")
    h = Harness(HttpResponse(status, {"Location": SENTINEL}, body))
    with pytest.raises(MetricoolError) as info:
        h.client.schedule_post(draft())
    err = info.value
    assert err.code == "api_error"
    assert err.status == status
    assert len(str(err)) <= 200
    assert SENTINEL not in str(err)
    assert SENTINEL not in repr(err)
    assert SENTINEL not in repr(h.client)
    assert SENTINEL not in str(h.client)


def test_transport_failure_becomes_api_error_without_details() -> None:
    h = Harness(OSError(f"connect failed {SENTINEL}"))
    with pytest.raises(MetricoolError) as info:
        h.client.schedule_post(draft())
    assert info.value.code == "api_error"
    assert info.value.status is None
    assert str(info.value) == "transport failure: OSError"
    assert info.value.__cause__ is None
    assert h.events[0]["status"] == 0


def test_oversized_body_raises_too_large() -> None:
    h = Harness(HttpResponse(200, {}, b"x" * 101), max_response_bytes=100)
    with pytest.raises(MetricoolError) as info:
        h.client.schedule_post(draft())
    assert (info.value.code, info.value.status) == ("too_large", 200)


def test_oversized_error_body_raises_too_large() -> None:
    h = Harness(HttpResponse(500, {}, b"x" * 101), max_response_bytes=100)
    with pytest.raises(MetricoolError) as info:
        h.client.schedule_post(draft())
    assert info.value.code == "too_large"


def test_body_of_exactly_the_limit_is_accepted() -> None:
    body = b'{"id":"a"}' + b" " * 90
    h = Harness(HttpResponse(200, {}, body), max_response_bytes=100)
    assert len(body) == 100
    assert h.client.schedule_post(draft()) == "a"


@pytest.mark.parametrize(
    "body",
    [b"<html>", b"", b"\xff\xfe\xfa", b"[" * 100_000, b'{"id": '],
)
def test_non_json_bodies_raise_invalid_response(body: bytes) -> None:
    h = Harness(HttpResponse(200, {}, body))
    with pytest.raises(MetricoolError) as info:
        h.client.schedule_post(draft())
    assert info.value.code == "invalid_response"


# ------------------------------------------------------------- events


def test_on_event_payloads_only_carry_safe_keys() -> None:
    h = Harness(reply({}, 429), reply({"id": "post-9"}))
    h.client.schedule_post(draft())
    assert h.events == [
        {"method": "POST", "path": "/v1/posts", "status": 429, "attempt": 1},
        {"method": "POST", "path": "/v1/posts", "status": 200, "attempt": 2},
    ]
    for event in h.events:
        assert set(event) == {"method", "path", "status", "attempt"}
        blob = json.dumps(event)
        assert SENTINEL not in blob
        assert "userId" not in blob
        assert "hello" not in blob
        assert "?" not in blob


def test_failing_callback_does_not_break_the_request(caplog: pytest.LogCaptureFixture) -> None:
    def boom(event: Any) -> None:
        raise RuntimeError(SENTINEL)

    transport = FakeTransport(reply({"id": "ok"}))
    client = build(transport=transport, on_event=boom)
    with caplog.at_level(logging.DEBUG, logger="metricool_client"):
        assert client.schedule_post(draft()) == "ok"
    assert "RuntimeError" in caplog.text
    assert SENTINEL not in caplog.text
    assert "hello world" not in caplog.text


# ------------------------------------------------------- constructor


BAD_CTOR: list[dict[str, Any]] = [
    {"user_token": ""},
    {"user_token": "a\nb"},
    {"user_token": "x" * 4097},
    {"user_token": 5},
    {"user_id": ""},
    {"user_id": 5},
    {"blog_id": "a b"},
    {"blog_id": "x" * 129},
    {"base_url": "http://app.metricool.com/api"},
    {"base_url": "https://host.example@evil.example/api"},
    {"base_url": "https://host.example/api?x=1"},
    {"base_url": "https://host.example/api#frag"},
    {"base_url": "https:///api"},
    {"base_url": "https://host.example/a b"},
    {"base_url": "https://[::1/api"},
    {"base_url": 5},
    {"endpoints": 5},
    {"endpoints": {"schedule_post": "/v1/posts"}},
    {"endpoints": {"schedule_post": "/v1/posts", "list_comments": "v1/comments"}},
    {"endpoints": {"schedule_post": "//evil.example/x", "list_comments": "/c"}},
    {"endpoints": {"schedule_post": "/a?b=1", "list_comments": "/c"}},
    {"endpoints": {"schedule_post": "/a b", "list_comments": "/c"}},
    {"endpoints": {"schedule_post": "/../a", "list_comments": "/c"}},
    {"endpoints": {"schedule_post": 5, "list_comments": "/c"}},
    {"max_retries": -1},
    {"max_retries": 11},
    {"max_retries": True},
    {"max_pages": 0},
    {"max_response_bytes": 0},
    {"transport": object()},
    {"on_event": "nope"},
    {"sleep": None},
]


@pytest.mark.parametrize("over", BAD_CTOR)
def test_constructor_rejects_invalid_arguments(over: dict[str, Any]) -> None:
    with pytest.raises(MetricoolError) as info:
        build(**over)
    assert info.value.code == "invalid_input"
    assert SENTINEL not in str(info.value)


def test_constructor_defaults_and_repr() -> None:
    client = build()
    assert repr(client) == "MetricoolClient(base_url='https://app.metricool.com/api')"
    assert SENTINEL not in repr(client)


def test_custom_base_url_with_trailing_slash() -> None:
    h = Harness(reply({"id": "x"}), base_url="https://example.test/api/")
    h.client.schedule_post(draft())
    assert h.transport.calls[0].url.startswith("https://example.test/api/v1/posts?")


# ---------------------------------------------------------------- CSV


def comment(**over: Any) -> Comment:
    fields: dict[str, Any] = {
        "id": "c1",
        "network": "facebook",
        "author": "Ana",
        "text": "hi",
        "created_at": AWARE,
        "post_id": "p1",
    }
    fields.update(over)
    return Comment(**fields)


def read_csv(text: str) -> list[list[str]]:
    return list(csv.reader(io.StringIO(text, newline="")))


FORMULA_CELLS = ["=1+1", "+1", "-5", "@x", "\t=1", "\r=1"]


@pytest.mark.parametrize("cell", FORMULA_CELLS)
def test_csv_prefixes_formula_cells(cell: str) -> None:
    out = io.StringIO()
    assert export_comments_csv([comment(text=cell)], out) == 1
    rows = read_csv(out.getvalue())
    assert rows[1][5] == "'" + cell


def test_csv_header_count_and_plain_cells() -> None:
    out = io.StringIO()
    count = export_comments_csv([comment(), comment(id="c2", text="a=b")], out)
    assert count == 2
    lines = out.getvalue().split("\r\n")
    assert lines[0] == "id,network,post_id,created_at,author,text"
    assert lines[1] == "c1,facebook,p1,2026-01-02T09:30:00-05:00,Ana,hi"
    assert lines[2].endswith(",a=b")
    assert lines[3] == ""


def test_csv_guards_every_column() -> None:
    out = io.StringIO()
    bad = comment(id="@1", network="+x", post_id="-1", author="=cmd", text="ok")
    export_comments_csv([bad], out)
    row = read_csv(out.getvalue())[1]
    assert row[0] == "'@1"
    assert row[1] == "'+x"
    assert row[2] == "'-1"
    assert row[3] == "2026-01-02T09:30:00-05:00"
    assert row[4] == "'=cmd"
    assert row[5] == "ok"


def test_csv_quotes_delimiters_and_roundtrips() -> None:
    out = io.StringIO()
    text = 'say "hi", ok\nbye'
    export_comments_csv(iter([comment(text=text)]), out)
    assert read_csv(out.getvalue())[1][5] == text


def test_csv_of_nothing_is_only_the_header() -> None:
    out = io.StringIO()
    assert export_comments_csv([], out) == 0
    assert out.getvalue() == "id,network,post_id,created_at,author,text\r\n"


def test_csv_max_rows_is_enforced() -> None:
    with pytest.raises(MetricoolError) as info:
        export_comments_csv([comment(), comment()], io.StringIO(), max_rows=1)
    assert info.value.code == "too_large"
    assert export_comments_csv([], io.StringIO(), max_rows=0) == 0


@pytest.mark.parametrize("limit", [-1, True, "3"])
def test_csv_rejects_bad_max_rows(limit: Any) -> None:
    out = io.StringIO()
    with pytest.raises(MetricoolError) as info:
        export_comments_csv([], out, max_rows=limit)
    assert info.value.code == "invalid_input"
    assert out.getvalue() == ""


@pytest.mark.parametrize(
    "bad",
    ["not a comment", comment(text=5), comment(created_at="2026-01-02")],
)
def test_csv_rejects_invalid_items(bad: Any) -> None:
    with pytest.raises(MetricoolError) as info:
        export_comments_csv([bad], io.StringIO())
    assert info.value.code == "invalid_input"


# ---------------------------------------------------------- transport


class FakeResponse:
    status = 200

    def __init__(self, body: bytes) -> None:
        self.headers = Message()
        self.headers["Content-Type"] = "application/json"
        self._body = body

    def read(self, limit: int = -1) -> bytes:
        return self._body if limit < 0 else self._body[:limit]

    def __enter__(self) -> FakeResponse:
        return self

    def __exit__(self, *exc: object) -> None:
        return None


class FakeOpener:
    def __init__(self, result: Any) -> None:
        self.result = result
        self.requests: list[urllib.request.Request] = []
        self.timeouts: list[float | None] = []

    def open(self, request: urllib.request.Request, timeout: float | None = None) -> Any:
        self.requests.append(request)
        self.timeouts.append(timeout)
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


def test_urllib_transport_returns_the_response() -> None:
    transport = UrllibTransport(timeout=5.0)
    opener = FakeOpener(FakeResponse(b'{"ok":true}'))
    transport._opener = opener  # type: ignore[assignment]
    url = "https://app.metricool.com/api/x?userId=1"
    response = transport.send("POST", url, {"X-Mc-Auth": SENTINEL}, b"{}")
    assert response.status == 200
    assert response.body == b'{"ok":true}'
    assert response.headers == {"Content-Type": "application/json"}
    request = opener.requests[0]
    assert request.full_url == url
    assert request.get_method() == "POST"
    assert request.data == b"{}"
    assert request.get_header("X-mc-auth") == SENTINEL
    assert opener.timeouts == [5.0]


def test_urllib_transport_returns_non_2xx_instead_of_raising() -> None:
    headers = Message()
    headers["Location"] = "https://evil.example/"
    error = urllib.error.HTTPError(
        "https://app.metricool.com/x",
        302,
        "Found",
        headers,
        io.BytesIO(b"moved"),
    )
    transport = UrllibTransport()
    transport._opener = FakeOpener(error)  # type: ignore[assignment]
    response = transport.send("GET", "https://app.metricool.com/x", {}, None)
    assert response.status == 302
    assert response.body == b"moved"
    assert response.headers == {"Location": "https://evil.example/"}


def test_urllib_transport_caps_the_bytes_it_reads() -> None:
    transport = UrllibTransport(max_read_bytes=4)
    transport._opener = FakeOpener(FakeResponse(b"0123456789"))  # type: ignore[assignment]
    response = transport.send("GET", "https://app.metricool.com/x", {}, None)
    assert response.body == b"0123"


def test_urllib_transport_propagates_network_errors() -> None:
    transport = UrllibTransport()
    transport._opener = FakeOpener(urllib.error.URLError("down"))  # type: ignore[assignment]
    with pytest.raises(urllib.error.URLError):
        transport.send("GET", "https://app.metricool.com/x", {}, None)


@pytest.mark.parametrize(
    "url",
    [
        "http://app.metricool.com/x",
        "file:///etc/passwd",
        "ftp://app.metricool.com/x",
        "https://",
        "https:/app.metricool.com",
        "//app.metricool.com/x",
        "https://[::1/x",
    ],
)
def test_urllib_transport_accepts_only_https(url: str) -> None:
    opener = FakeOpener(FakeResponse(b""))
    transport = UrllibTransport()
    transport._opener = opener  # type: ignore[assignment]
    with pytest.raises(MetricoolError) as info:
        transport.send("GET", url, {}, None)
    assert info.value.code == "invalid_input"
    assert opener.requests == []


@pytest.mark.parametrize("timeout", [0, -1, True, "5", float("nan"), float("inf")])
def test_urllib_transport_rejects_bad_timeouts(timeout: Any) -> None:
    with pytest.raises(MetricoolError) as info:
        UrllibTransport(timeout=timeout)
    assert info.value.code == "invalid_input"


@pytest.mark.parametrize("limit", [0, -5, True, "x"])
def test_urllib_transport_rejects_bad_read_limits(limit: Any) -> None:
    with pytest.raises(MetricoolError) as info:
        UrllibTransport(max_read_bytes=limit)
    assert info.value.code == "invalid_input"


def test_redirects_are_refused() -> None:
    handler = transport_module._NoRedirectHandler()
    request = urllib.request.Request("https://app.metricool.com/a")
    refused = handler.redirect_request(
        request,
        io.BytesIO(b""),
        302,
        "Found",
        Message(),  # type: ignore[arg-type]
        "https://evil.example/",
    )
    assert refused is None
    opener = transport_module._build_opener()
    assert any(isinstance(h, transport_module._NoRedirectHandler) for h in opener.handlers)
    assert not any(type(h) is urllib.request.HTTPRedirectHandler for h in opener.handlers)
