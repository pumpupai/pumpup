"""Poll + resume logic for the "pumpup" gateway platform: poll Pump Up for decisions and resume the
origin Hermes session when one lands. Resume is an outbound localhost POST to the API server, so it works
for every deployment shape, including a fully NAT'd host a webhook could never reach.

Host-free by design (no `gateway.*` imports) so it stays unit-testable and importable in the OSS mirror;
the BasePlatformAdapter shell that drives this loop lives in `adapter.py`.
"""

from __future__ import annotations

import enum
import json
import logging
from typing import Any

import httpx
from pumpup import AsyncPumpUp

from .config import Config
from .state import Breadcrumb, BreadcrumbStore
from .tools import fetch_result

logger = logging.getLogger(__name__)

# The resume POST blocks until the resumed turn completes; allow a full turn (Hermes tools cap at 300s).
RESUME_TIMEOUT_SEC = 300.0
HEALTH_TIMEOUT_SEC = 5.0
# Failed resumes per request before we give up and drop the breadcrumb. ~10 min at the default 30s
# interval — long enough to ride out a gateway deploy, short enough to bound a poison turn.
MAX_RESUME_ATTEMPTS = 20


class _ResumeOutcome(enum.Enum):
    """How an attempted resume settled: DELIVERED (the turn ran), GONE (session unresumable — drop), or
    RETRY (transient — the API server may be down/restarting)."""

    DELIVERED = enum.auto()
    GONE = enum.auto()
    RETRY = enum.auto()


def _format_decision(crumb: Breadcrumb, result: Any) -> str:
    """The user message injected into the resumed session: what was decided, with the full result payload."""
    payload = json.dumps(result.model_dump(mode="json", by_alias=True))
    return (
        f'Your Pump Up {crumb.type} request "{crumb.summary}" (id {crumb.request_id}) has been decided by a '
        f"human. Act on this decision now:\n{payload}"
    )


async def run_poll_cycle(client: AsyncPumpUp, store: BreadcrumbStore, http: httpx.AsyncClient, cfg: Config) -> None:
    """One poll pass: for each open request, fetch its decision and, once decided, resume its origin session.
    A single request's failure is logged and skipped so one bad breadcrumb never stalls the others."""
    for crumb in store.list_open():
        try:
            await _resume_if_decided(client, store, http, cfg, crumb)
        except Exception:
            logger.exception("pumpup: error handling request %s", crumb.request_id)


async def _resume_if_decided(
    client: AsyncPumpUp, store: BreadcrumbStore, http: httpx.AsyncClient, cfg: Config, crumb: Breadcrumb
) -> None:
    """Poll one request; once decided, resume its origin session and settle the breadcrumb accordingly.
    (A fetch_result error propagates to the caller — it's a poll failure, not a resume attempt, so it
    charges nothing against the cap.)"""
    result = await fetch_result(client, crumb.type, crumb.request_id)
    if result is None:
        return  # still pending
    match await _attempt_resume(http, cfg, crumb, result):
        case _ResumeOutcome.DELIVERED | _ResumeOutcome.GONE:
            store.clear(crumb.request_id)  # acted on, or the session is gone (unresumable) — done with it
        case _ResumeOutcome.RETRY:
            _bump_or_drop(store, crumb)  # transient or poison — retry next cycle, give up past the cap


async def _attempt_resume(http: httpx.AsyncClient, cfg: Config, crumb: Breadcrumb, result: object) -> _ResumeOutcome:
    """POST the decision into the origin session and classify the outcome: DELIVERED (2xx), GONE (404 —
    session rolled/ended, unresumable), or RETRY (any other status or a connection error — server down)."""
    message = _format_decision(crumb, result)
    url = f"http://{cfg.api_server_host}:{cfg.api_server_port}/api/sessions/{crumb.session_id}/chat"
    headers = {"Authorization": f"Bearer {cfg.api_server_key}"}
    try:
        response = await http.post(url, json={"message": message}, headers=headers, timeout=RESUME_TIMEOUT_SEC)
    except httpx.HTTPError as exc:
        logger.warning("pumpup: resume of request %s could not reach the API server (%s)", crumb.request_id, exc)
        return _ResumeOutcome.RETRY
    if response.status_code == 404:
        logger.error(
            "pumpup: session %s is gone; dropping decided request %s (session rehydration is deferred)",
            crumb.session_id,
            crumb.request_id,
        )
        return _ResumeOutcome.GONE
    if response.is_success:
        return _ResumeOutcome.DELIVERED
    logger.warning("pumpup: resume of request %s failed (HTTP %d)", crumb.request_id, response.status_code)
    return _ResumeOutcome.RETRY


def _bump_or_drop(store: BreadcrumbStore, crumb: Breadcrumb) -> None:
    """Charge a failed resume attempt; keep the breadcrumb for the next cycle, or drop it once the attempts
    reach the cap (a poison turn or an outage longer than the retry window)."""
    attempts = crumb.attempts + 1
    if attempts >= MAX_RESUME_ATTEMPTS:
        logger.error("pumpup: giving up on request %s after %d failed resume attempts", crumb.request_id, attempts)
        store.clear(crumb.request_id)
    else:
        store.record(crumb.model_copy(update={"attempts": attempts}))


async def probe_api_server(http: httpx.AsyncClient, cfg: Config) -> None:
    """GET /health on the local API server; log loudly if it's unreachable — resumes need it up."""
    url = f"http://{cfg.api_server_host}:{cfg.api_server_port}/health"
    try:
        response = await http.get(url, timeout=HEALTH_TIMEOUT_SEC)
        response.raise_for_status()
    except Exception as exc:  # noqa: BLE001 — a failed probe is informational, not fatal; the loop still starts
        logger.error(
            "pumpup: API server health check failed at %s (%s) — resumes will fail until it is up "
            "(the gateway needs API_SERVER_ENABLED=true with API_SERVER_KEY set)",
            url,
            exc,
        )
