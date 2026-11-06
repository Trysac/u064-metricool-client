"""Request and response field mapping between this library and the Metricool API.

The base URL, the ``X-Mc-Auth`` header, and the ``userId`` and ``blogId`` query
parameters were verified on 2026-11-05 at app.metricool.com/resources/apidocs.
The endpoint paths were NOT verifiable, so the caller supplies them. The JSON
field names below are this library's documented mapping: they MUST be checked
against the Metricool API guide before each release.

Request to schedule a post (``POST``): JSON object with ``text``, ``networks``
(list), ``publishAt`` (ISO 8601 with offset, whole seconds) and ``media`` (list).
Response: JSON object with ``id``.

Request for comments (``GET``): query ``network``, ``start``, ``end`` (ISO dates),
``page`` (1-based) and ``pageSize``. Response: JSON object with ``comments``, a
list of objects with ``id``, ``text``, ``author``, ``postId``, ``network`` and
``createdAt`` (ISO 8601 with offset; ``Z`` is accepted).
"""

from __future__ import annotations

from datetime import date, datetime

from ._errors import MetricoolError
from ._models import Comment, PostDraft

SCHEDULE_POST = "schedule_post"
LIST_COMMENTS = "list_comments"

_MAX_ITEMS_PER_PAGE = 10_000
_MAX_ID_CHARS = 200
_MAX_TIMESTAMP_CHARS = 64


def _bad(message: str) -> MetricoolError:
    return MetricoolError("invalid_response", message)


def schedule_query(user_id: str, blog_id: str) -> dict[str, str]:
    """Return the query parameters of the schedule request."""
    return {"userId": user_id, "blogId": blog_id}


def schedule_payload(post: PostDraft) -> dict[str, object]:
    """Return the JSON body of the schedule request."""
    post._validate()
    return {
        "text": post.text,
        "networks": list(post.networks),
        "publishAt": post.publish_at.isoformat(timespec="seconds"),
        "media": list(post.media_urls),
    }


def parse_post_id(data: object) -> str:
    """Extract the created post id from a decoded schedule response."""
    if not isinstance(data, dict):
        raise _bad("response must be a JSON object")
    value = data.get("id")
    if isinstance(value, bool) or not isinstance(value, str | int):
        raise _bad("response has no post id")
    post_id = str(value)
    if not post_id or len(post_id) > _MAX_ID_CHARS:
        raise _bad("response has an invalid post id")
    return post_id


def comments_query(
    user_id: str,
    blog_id: str,
    network: str,
    start: date,
    end: date,
    page: int,
    page_size: int,
) -> dict[str, str]:
    """Return the query parameters of one comments page request."""
    return {
        "userId": user_id,
        "blogId": blog_id,
        "network": network,
        "start": start.isoformat(),
        "end": end.isoformat(),
        "page": str(page),
        "pageSize": str(page_size),
    }


def _text_field(item: dict[str, object], key: str, *, required: bool) -> str:
    value = item.get(key)
    if value is None:
        if required:
            raise _bad(f"comment field {key} is missing")
        return ""
    if isinstance(value, bool) or not isinstance(value, str | int):
        raise _bad(f"comment field {key} has an invalid value")
    text = str(value)
    if required and not text:
        raise _bad(f"comment field {key} is empty")
    return text


def _parse_timestamp(value: object) -> datetime:
    if not isinstance(value, str) or not 1 <= len(value) <= _MAX_TIMESTAMP_CHARS:
        raise _bad("comment createdAt must be an ISO 8601 string")
    text = value[:-1] + "+00:00" if value[-1] in "Zz" else value
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        raise _bad("comment createdAt is not a valid timestamp") from None
    if parsed.utcoffset() is None:
        raise _bad("comment createdAt must include a UTC offset")
    return parsed


def _parse_comment(item: object, network: str) -> Comment:
    if not isinstance(item, dict):
        raise _bad("comment must be a JSON object")
    item_network = item.get("network")
    return Comment(
        id=_text_field(item, "id", required=True),
        network=item_network if isinstance(item_network, str) and item_network else network,
        author=_text_field(item, "author", required=False),
        text=_text_field(item, "text", required=False),
        created_at=_parse_timestamp(item.get("createdAt")),
        post_id=_text_field(item, "postId", required=False),
    )


def parse_comments_page(data: object, network: str) -> list[Comment]:
    """Convert one decoded comments response into ``Comment`` objects."""
    if not isinstance(data, dict):
        raise _bad("response must be a JSON object")
    items = data.get("comments")
    if not isinstance(items, list):
        raise _bad("response has no comments list")
    if len(items) > _MAX_ITEMS_PER_PAGE:
        raise _bad("response page has too many comments")
    return [_parse_comment(item, network) for item in items]
