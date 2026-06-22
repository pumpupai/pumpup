"""Pump Up × Hermes plugin — request human approvals/elicitations and resume agent work on the
decision. Design: this repo's tech-docs/current/hermes-plugin.md.

register(ctx) wires the six pumpup_* tools and the background "pumpup" gateway platform that polls
Pump Up for decisions and resumes the origin session via the local API server.
"""

from __future__ import annotations

import logging

from .tools import register_capture_tools, register_request_tools

logger = logging.getLogger(__name__)


def register(ctx) -> None:
    """Plugin entry point, called once by the Hermes plugin loader."""
    # Deferred: adapter.py imports the host `gateway.*`, only present in-host (keeps the package importable
    # for tests / the OSS mirror). register() only ever runs inside Hermes, so the import resolves there.
    from .adapter import register_poll_platform

    register_request_tools(ctx)
    register_capture_tools(ctx)
    register_poll_platform(ctx)
    logger.info("pumpup: plugin loaded")
