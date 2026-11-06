"""Typed client core for the Metricool API."""

from __future__ import annotations

import logging

from ._client import MetricoolClient
from ._csv import export_comments_csv
from ._errors import ErrorCode, MetricoolError
from ._models import KNOWN_NETWORKS, Comment, PostDraft
from ._transport import HttpResponse, Transport, UrllibTransport

__all__ = [
    "KNOWN_NETWORKS",
    "Comment",
    "ErrorCode",
    "HttpResponse",
    "MetricoolClient",
    "MetricoolError",
    "PostDraft",
    "Transport",
    "UrllibTransport",
    "__version__",
    "export_comments_csv",
]

__version__ = "0.1.0"

logging.getLogger(__name__).addHandler(logging.NullHandler())
