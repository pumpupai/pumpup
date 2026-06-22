"""The shared Pump Up async SDK client — one process-wide instance for all tools and the poll loop."""

from __future__ import annotations

import threading

from pumpup import AsyncPumpUp

from .config import load_config

_client: AsyncPumpUp | None = None
_lock = threading.Lock()


def get_client() -> AsyncPumpUp:
    """Return the process-wide AsyncPumpUp, built once on first use.

    A single shared client is safe: httpx tolerates use across the per-thread event loops Hermes
    spins up for tool dispatch (verified), and the poll loop runs on the gateway's own loop. Built
    lazily so the plugin still loads when Pump Up isn't configured (tools + platform gate on that).
    """
    global _client
    if _client is None:
        with _lock:
            if _client is None:
                config = load_config()
                _client = AsyncPumpUp(base_url=config.base_url, api_key=config.api_key)
    return _client
