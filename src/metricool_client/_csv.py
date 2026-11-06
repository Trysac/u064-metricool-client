"""CSV export with CSV (formula) injection protection."""

from __future__ import annotations

import csv
from collections.abc import Iterable
from datetime import datetime
from typing import TextIO

from ._errors import MetricoolError
from ._models import Comment

HEADER = ("id", "network", "post_id", "created_at", "author", "text")

# OWASP CSV Injection: cells starting with these characters may run as formulas.
_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")
_DEFAULT_MAX_ROWS = 1_000_000


def _guard(cell: str) -> str:
    return "'" + cell if cell.startswith(_FORMULA_PREFIXES) else cell


def _row(comment: object) -> list[str]:
    if not isinstance(comment, Comment):
        raise MetricoolError("invalid_input", "comments must contain Comment objects")
    fields = (comment.id, comment.network, comment.post_id, comment.author, comment.text)
    if not all(isinstance(field, str) for field in fields):
        raise MetricoolError("invalid_input", "comment fields must be strings")
    if not isinstance(comment.created_at, datetime):
        raise MetricoolError("invalid_input", "comment created_at must be a datetime")
    ident, network, post_id, author, text = fields
    cells = [ident, network, post_id, comment.created_at.isoformat(), author, text]
    return [_guard(cell) for cell in cells]


def export_comments_csv(
    comments: Iterable[Comment],
    out: TextIO,
    *,
    max_rows: int = _DEFAULT_MAX_ROWS,
) -> int:
    """Write ``comments`` to ``out`` as RFC 4180 CSV and return the row count.

    The header is ``id,network,post_id,created_at,author,text``. Lines end with
    CRLF, so open file objects with ``newline=""``. Every cell starting with
    ``=``, ``+``, ``-``, ``@``, a tab or a carriage return is prefixed with a
    single quote (OWASP CSV Injection guard). Rows already written stay in
    ``out`` if a later row is invalid.

    Raises:
        MetricoolError: ``invalid_input`` for a bad item or ``max_rows``, and
            ``too_large`` when more than ``max_rows`` comments are given.
    """
    if isinstance(max_rows, bool) or not isinstance(max_rows, int) or max_rows < 0:
        raise MetricoolError("invalid_input", "max_rows must be a non-negative integer")
    writer = csv.writer(out, quoting=csv.QUOTE_MINIMAL, lineterminator="\r\n")
    writer.writerow(HEADER)
    count = 0
    for comment in comments:
        if count >= max_rows:
            raise MetricoolError("too_large", "more comments than max_rows")
        writer.writerow(_row(comment))
        count += 1
    return count
