"""Poll + resume policy — the core of Group 4. Each test drives one cycle (or a capped loop) with a
mocked SDK result and a mocked resume POST, asserting how the breadcrumb settles."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import httpx

from pumpup_hermes import poll
from pumpup_hermes.config import load_config
from pumpup_hermes.state import Breadcrumb, BreadcrumbStore


def _crumb(request_id="r1", kind="approval", attempts=0) -> Breadcrumb:
    return Breadcrumb(
        request_id=request_id, session_id="sA", type=kind, summary="ship it?", created_at="t", attempts=attempts
    )


def _store(tmp_path, *crumbs) -> BreadcrumbStore:
    store = BreadcrumbStore(tmp_path / "pending.json")
    for crumb in crumbs:
        store.record(crumb)
    return store


def _decided() -> MagicMock:
    result = MagicMock()
    result.model_dump.return_value = {"outcome": {"type": "APPROVE"}, "decidedBy": "u1"}
    return result


def _client(kind="approvals", value=None) -> MagicMock:
    client = MagicMock()
    getattr(client, kind).get_result = AsyncMock(return_value=value)
    return client


def _http_status(code) -> MagicMock:
    http = MagicMock()
    response = MagicMock(status_code=code, is_success=200 <= code < 300)
    http.post = AsyncMock(return_value=response)
    return http


def _http_raising(exc) -> MagicMock:
    http = MagicMock()
    http.post = AsyncMock(side_effect=exc)
    return http


async def test_pending_keeps_and_does_not_post(tmp_path):
    store = _store(tmp_path, _crumb())
    http = _http_status(200)
    await poll.run_poll_cycle(_client("approvals", None), store, http, load_config())
    http.post.assert_not_awaited()
    assert len(store.list_open()) == 1


async def test_decided_posts_to_origin_session_and_clears(tmp_path):
    store = _store(tmp_path, _crumb())
    http = _http_status(200)
    await poll.run_poll_cycle(_client("approvals", _decided()), store, http, load_config())
    args, kwargs = http.post.await_args
    assert args[0] == "http://127.0.0.1:8642/api/sessions/sA/chat"
    assert kwargs["headers"]["Authorization"] == "Bearer secret"
    assert "ship it?" in kwargs["json"]["message"] and "APPROVE" in kwargs["json"]["message"]
    assert store.list_open() == []


async def test_session_gone_drops(tmp_path):
    store = _store(tmp_path, _crumb())
    await poll.run_poll_cycle(_client("approvals", _decided()), store, _http_status(404), load_config())
    assert store.list_open() == []


async def test_server_error_keeps_and_charges_an_attempt(tmp_path):
    store = _store(tmp_path, _crumb())
    await poll.run_poll_cycle(_client("approvals", _decided()), store, _http_status(503), load_config())
    open_now = store.list_open()
    assert len(open_now) == 1 and open_now[0].attempts == 1


async def test_connection_error_keeps_and_charges_an_attempt(tmp_path):
    store = _store(tmp_path, _crumb())
    http = _http_raising(httpx.ConnectError("refused"))
    await poll.run_poll_cycle(_client("approvals", _decided()), store, http, load_config())
    assert store.list_open()[0].attempts == 1


async def test_persistent_failure_drops_at_the_cap(tmp_path):
    store = _store(tmp_path, _crumb())
    http = _http_status(500)
    cycles = 0
    while store.list_open():
        await poll.run_poll_cycle(_client("approvals", _decided()), store, http, load_config())
        cycles += 1
        assert cycles <= poll.MAX_RESUME_ATTEMPTS  # must not loop past the cap
    assert cycles == poll.MAX_RESUME_ATTEMPTS


async def test_fetch_error_does_not_charge_an_attempt(tmp_path):
    """A failed result-poll (Pump Up GET) is a poll failure, not a resume attempt — it must not bump."""
    store = _store(tmp_path, _crumb())
    client = MagicMock()
    client.approvals.get_result = AsyncMock(side_effect=RuntimeError("pump up down"))
    await poll.run_poll_cycle(client, store, _http_status(200), load_config())
    open_now = store.list_open()
    assert len(open_now) == 1 and open_now[0].attempts == 0


async def test_elicitation_polls_the_elicitation_result(tmp_path):
    store = _store(tmp_path, _crumb(kind="elicitation"))
    client = _client("elicitations", _decided())
    await poll.run_poll_cycle(client, store, _http_status(200), load_config())
    client.elicitations.get_result.assert_awaited_once_with("r1")
    assert store.list_open() == []
