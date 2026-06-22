"""Breadcrumb store: the behaviour that matters is durability — a gateway restart must re-find open
requests, and a cleared one must stay gone."""

from __future__ import annotations

from pumpup_hermes.state import Breadcrumb, BreadcrumbStore


def _crumb(request_id: str = "r1") -> Breadcrumb:
    return Breadcrumb(request_id=request_id, session_id="sA", type="approval", summary="s", created_at="t")


def test_record_survives_a_fresh_store(tmp_path):
    """A fresh store at the same path (a restart) re-reads the persisted open requests."""
    path = tmp_path / "pending.json"
    BreadcrumbStore(path).record(_crumb("r1"))
    assert [c.request_id for c in BreadcrumbStore(path).list_open()] == ["r1"]


def test_clear_is_persisted(tmp_path):
    path = tmp_path / "pending.json"
    store = BreadcrumbStore(path)
    store.record(_crumb("r1"))
    store.record(_crumb("r2"))
    store.clear("r1")
    assert {c.request_id for c in BreadcrumbStore(path).list_open()} == {"r2"}


def test_record_replaces_same_id(tmp_path):
    """A re-record (e.g. an attempts bump) replaces rather than duplicates the breadcrumb."""
    path = tmp_path / "pending.json"
    store = BreadcrumbStore(path)
    store.record(_crumb("r1"))
    store.record(Breadcrumb(request_id="r1", session_id="sA", type="approval", summary="s", created_at="t", attempts=3))
    open_now = store.list_open()
    assert len(open_now) == 1 and open_now[0].attempts == 3


def test_missing_file_is_empty(tmp_path):
    assert BreadcrumbStore(tmp_path / "nope.json").list_open() == []
