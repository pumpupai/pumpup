"""Plugin config from env. PUMPUP_* gate and drive the tools; API_SERVER_* drive resume.

The API server values mirror Hermes's own gateway env (no duplication) — resume POSTs to the
local API server, which the gateway already runs when API_SERVER_ENABLED=true.
"""

from __future__ import annotations

import os
from pathlib import Path

from pydantic import Field, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Config(BaseSettings):
    """Validated env config. Required values (base_url / api_key / api_server_key) and the bounds below
    raise at construction — a missing/invalid value is a deploy mistake, surfaced loudly, not at runtime."""

    model_config = SettingsConfigDict(frozen=True)

    base_url: str = Field(validation_alias="PUMPUP_BASE_URL")
    api_key: str = Field(validation_alias="PUMPUP_API_KEY")
    poll_interval_sec: float = Field(default=30.0, gt=0, validation_alias="PUMPUP_POLL_INTERVAL_SEC")
    api_server_host: str = Field(default="127.0.0.1", validation_alias="API_SERVER_HOST")
    api_server_port: int = Field(default=8642, ge=1, le=65535, validation_alias="API_SERVER_PORT")
    api_server_key: str = Field(min_length=1, validation_alias="API_SERVER_KEY")

    @computed_field  # type: ignore[prop-decorator]
    @property
    def state_path(self) -> Path:
        """Breadcrumb store location under the Hermes home — derived, never an env var."""
        return _hermes_home() / "pumpup" / "pending.json"


def is_configured() -> bool:
    """True when Pump Up credentials are present — the check_fn that gates tools and the poll platform.
    Reads env directly (not a full Config build) since it runs before the resume values are needed."""
    return bool(os.getenv("PUMPUP_BASE_URL") and os.getenv("PUMPUP_API_KEY"))


def load_config() -> Config:
    """Build the validated config from env; raises pydantic ValidationError on a missing/invalid value."""
    return Config()


def _hermes_home() -> Path:
    """The Hermes home dir via the host resolver (HERMES_HOME / profile / platform default), matching
    the sibling plugins; falls back to env/default when imported outside the host (our isolated tests)."""
    try:
        from hermes_constants import get_hermes_home
    except ImportError:
        return Path(os.getenv("HERMES_HOME", "~/.hermes")).expanduser()
    return get_hermes_home()
