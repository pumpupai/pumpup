"""Config validation: required values and bounds fail fast at load, not silently at runtime."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from pumpup_hermes.config import load_config


def test_missing_api_server_key_fails_fast(monkeypatch):
    """A blank/absent API_SERVER_KEY raises at load — closes the silent resume-auth drop."""
    monkeypatch.delenv("API_SERVER_KEY", raising=False)
    with pytest.raises(ValidationError):
        load_config()


def test_out_of_range_port_fails_fast(monkeypatch):
    """An API_SERVER_PORT outside 1-65535 raises at load rather than producing a bad resume URL."""
    monkeypatch.setenv("API_SERVER_PORT", "70000")
    with pytest.raises(ValidationError):
        load_config()
