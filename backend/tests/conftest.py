"""Shared test configuration.

``analytics`` caches the scored book in-process for speed, which is correct in
production where there is one database, but leaks between tests that point the
application at different files. Clearing it around every test keeps them
independent.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import analytics  # noqa: E402


@pytest.fixture(autouse=True)
def clear_analytics_cache():
    analytics.bump()
    yield
    analytics.bump()
