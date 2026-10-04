"""Shared pytest configuration."""

from __future__ import annotations

import os

from hypothesis import settings

# ``deadline=None`` keeps property tests from flaking on slow or shared machines
# (laptops on battery, Windows CI runners). Correctness is what we test here, not speed.
settings.register_profile("dev", max_examples=100, deadline=None)
settings.register_profile("ci", max_examples=300, deadline=None, print_blob=True)
settings.load_profile(os.getenv("HYPOTHESIS_PROFILE", "dev"))
