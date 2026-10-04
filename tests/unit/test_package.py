"""Smoke tests: the package imports and exposes a version."""

from __future__ import annotations

import re

import contam


def test_version_is_semver_like() -> None:
    assert re.fullmatch(r"\d+\.\d+\.\d+", contam.__version__)
