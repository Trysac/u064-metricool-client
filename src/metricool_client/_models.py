"""Immutable data models."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from urllib.parse import urlsplit

from ._errors import MetricoolError

_NETWORKS = (
    "bluesky",
    "facebook",
    "gmb",
    "instagram",
    "linkedin",
    "pinterest",
    "threads",
    "tiktok",
    "twitch",
    "twitter",
    "youtube",
)

KNOWN_NETWORKS: frozenset[str] = frozenset(_NETWORKS)
"""Networks accepted by this library (its own list, not fetched from the API)."""

MAX_TEXT_CHARS = 5000
MAX_MEDIA_URLS = 10
_MAX_URL_CHARS = 2048
_CONTROL_OR_SPACE = re.compile(r"[\x00-\x20\x7f]")


def _invalid(message: str) -> MetricoolError:
    return MetricoolError("invalid_input", message)


def _check_media_url(index: int, url: object) -> None:
    if not isinstance(url, str) or not 1 <= len(url) <= _MAX_URL_CHARS:
        raise _invalid(f"media_urls[{index}] must be a string of 1-2048 characters")
    if _CONTROL_OR_SPACE.search(url):
        raise _invalid(f"media_urls[{index}] contains whitespace or control characters")
    try:
        parts = urlsplit(url)
        host = parts.hostname
    except ValueError:
        raise _invalid(f"media_urls[{index}] is not a valid URL") from None
    if parts.scheme != "https" or not host or "@" in parts.netloc:
        raise _invalid(f"media_urls[{index}] must be an https URL without credentials")


@dataclass(frozen=True)
class PostDraft:
    """A post to schedule.

    Attributes:
        text: Post text, 1 to 5000 characters.
        networks: Non-empty tuple of distinct names from ``KNOWN_NETWORKS``.
        publish_at: Timezone-aware publication time.
        media_urls: At most 10 ``https`` URLs.

    Raises:
        MetricoolError: with code ``invalid_input`` when a field is invalid.
    """

    text: str
    networks: tuple[str, ...]
    publish_at: datetime
    media_urls: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        self._validate()

    def _validate(self) -> None:
        if not isinstance(self.text, str) or not 1 <= len(self.text) <= MAX_TEXT_CHARS:
            raise _invalid("text must be a string of 1 to 5000 characters")
        if not isinstance(self.networks, tuple) or not self.networks:
            raise _invalid("networks must be a non-empty tuple")
        for network in self.networks:
            if not isinstance(network, str) or network not in KNOWN_NETWORKS:
                raise _invalid("networks contains an unknown network")
        if len(set(self.networks)) != len(self.networks):
            raise _invalid("networks must not contain duplicates")
        if not isinstance(self.publish_at, datetime):
            raise _invalid("publish_at must be a datetime")
        if self.publish_at.tzinfo is None or self.publish_at.utcoffset() is None:
            raise _invalid("publish_at must be timezone-aware")
        if not isinstance(self.media_urls, tuple) or len(self.media_urls) > MAX_MEDIA_URLS:
            raise _invalid("media_urls must be a tuple of at most 10 URLs")
        for index, url in enumerate(self.media_urls):
            _check_media_url(index, url)


@dataclass(frozen=True)
class Comment:
    """A comment received on a post."""

    id: str
    network: str
    author: str
    text: str
    created_at: datetime
    post_id: str
