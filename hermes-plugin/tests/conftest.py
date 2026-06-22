"""Shared test setup: per-test env + temp Hermes home, and a reset of the process-wide singletons so the
cached client / breadcrumb store / task map never leak between tests."""

from __future__ import annotations

import pytest

from pumpup_hermes import client as client_mod
from pumpup_hermes import state as state_mod
from pumpup_hermes import tools as tools_mod


@pytest.fixture(autouse=True)
def env(monkeypatch, tmp_path):
    """Point config + state at a fresh temp dir and clear the cached singletons before each test."""
    for key, value in {
        "HERMES_HOME": str(tmp_path),
        "PUMPUP_BASE_URL": "https://api.test",
        "PUMPUP_API_KEY": "k",
        "API_SERVER_HOST": "127.0.0.1",
        "API_SERVER_PORT": "8642",
        "API_SERVER_KEY": "secret",
    }.items():
        monkeypatch.setenv(key, value)
    client_mod._client = None
    state_mod._store = None
    tools_mod._session_tasks.clear()
