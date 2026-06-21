"""Pytest configuration — hypothesis profiles for CI vs local."""

import os
from hypothesis import settings, HealthCheck

# CI profile: fast, lenient deadlines
settings.register_profile(
    "ci",
    max_examples=20,
    deadline=10000,
    suppress_health_check=[HealthCheck.too_slow],
)

# Local profile: thorough
settings.register_profile(
    "local",
    max_examples=200,
    deadline=5000,
)

# HYPOTHESIS_PROFILE=ci in CI, default to local
settings.load_profile(os.environ.get("HYPOTHESIS_PROFILE", "local"))
