"""The "pumpup" gateway platform adapter — host glue. Subclasses Hermes's BasePlatformAdapter, so this
module imports `gateway.*` and is only importable in-host; the package defers importing it to register(),
keeping poll.py's logic unit-testable without the host. Background-loop host only: it routes no inbound
messages (send / get_chat_info are inert); the loop resumes the origin session via the local API server.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx
from gateway.config import Platform, PlatformConfig
from gateway.platforms.base import BasePlatformAdapter, SendResult

from .client import get_client
from .config import is_configured, load_config
from .poll import probe_api_server, run_poll_cycle
from .state import get_store

logger = logging.getLogger(__name__)


class PumpUpPollAdapter(BasePlatformAdapter):
    """Background-loop host: no inbound routing (send / get_chat_info inert). The poll loop resumes the
    origin session via the local API server, so it works even on a fully NAT'd host."""

    def __init__(self, config: PlatformConfig) -> None:
        super().__init__(config, Platform("pumpup"))
        self._cfg = load_config()
        self._http = httpx.AsyncClient()
        self._task: asyncio.Task | None = None

    async def connect(self) -> bool:
        """Probe the local API server, then start the outbound poll loop on the gateway's event loop."""
        await probe_api_server(self._http, self._cfg)
        self._task = asyncio.create_task(self._run())
        self._background_tasks.add(self._task)
        self._task.add_done_callback(self._background_tasks.discard)
        return True

    async def disconnect(self) -> None:
        """Stop the poll loop and close the resume HTTP client."""
        if self._task is not None:
            self._task.cancel()
        await self._http.aclose()

    async def send(self, chat_id, content, reply_to=None, metadata=None) -> SendResult:
        """Inert — the pumpup platform never sends; it exists only to host the poll loop."""
        return SendResult(success=False, error="pumpup is a poll-only platform")

    async def get_chat_info(self, chat_id) -> dict:
        """Inert — the platform routes no inbound messages, so it owns no chats."""
        return {"name": "Pump Up", "type": "channel"}

    async def _run(self) -> None:
        """Poll for decisions every interval until cancelled; one cycle's failure never kills the loop."""
        while True:
            try:
                await run_poll_cycle(get_client(), get_store(), self._http, self._cfg)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("pumpup: poll cycle failed")
            await asyncio.sleep(self._cfg.poll_interval_sec)


def register_poll_platform(ctx: Any) -> None:
    """Register the background "pumpup" gateway platform (poll loop + origin-session resume)."""
    ctx.register_platform(
        name="pumpup",
        label="Pump Up",
        adapter_factory=lambda config: PumpUpPollAdapter(config),
        check_fn=is_configured,
    )
