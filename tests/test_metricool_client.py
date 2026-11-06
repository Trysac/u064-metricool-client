"""Behavior tests for the public API of metricool_client."""

from __future__ import annotations

import pytest

import metricool_client


def test_normalize_trims_and_lowercases() -> None:
    assert metricool_client.normalize("  Hello World ") == "hello world"


@pytest.mark.parametrize("value", ["", "   ", "\t\n"])
def test_normalize_rejects_blank_input(value: str) -> None:
    with pytest.raises(ValueError, match="must not be empty"):
        metricool_client.normalize(value)


def test_version_is_semver() -> None:
    parts = metricool_client.__version__.split(".")
    assert len(parts) == 3
    assert all(part.isdigit() for part in parts)
