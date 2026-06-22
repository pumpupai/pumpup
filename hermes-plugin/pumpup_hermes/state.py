"""Durable breadcrumb store: maps a parked Pump Up request to the Hermes session that opened it.

The only hand-rolled state the plugin keeps — Hermes exposes no durable-flow primitive. Persisted as a
small JSON file (pydantic, already in the tree via the SDK) so a gateway restart re-enumerates the open
waits and the poll loop resumes them.
"""

from __future__ import annotations

import threading
from pathlib import Path

from pydantic import BaseModel, ConfigDict, TypeAdapter

from .config import load_config


class Breadcrumb(BaseModel):
    """One parked request: the poll handle (request_id), the session a decision resumes, and its summary.
    `attempts` counts failed resumes — the poll loop drops the breadcrumb once it reaches the cap."""

    model_config = ConfigDict(frozen=True)

    request_id: str
    session_id: str
    type: str  # "approval" | "elicitation" — selects the result endpoint to poll
    summary: str
    created_at: str
    attempts: int = 0


_CRUMBS = TypeAdapter(list[Breadcrumb])


class BreadcrumbStore:
    """In-memory map of open requests, persisted to a JSON file on every mutation and lock-guarded for the
    poll loop and tool threads. The file is the source of truth — read on construction (restart recovery)."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._lock = threading.Lock()
        self._crumbs = _read(path)

    def record(self, crumb: Breadcrumb) -> None:
        """Add or replace a breadcrumb and persist (request create)."""
        with self._lock:
            self._crumbs[crumb.request_id] = crumb
            self._save()

    def clear(self, request_id: str) -> None:
        """Drop a breadcrumb once its decision is delivered (or abandoned) and persist."""
        with self._lock:
            if self._crumbs.pop(request_id, None) is not None:
                self._save()

    def list_open(self) -> list[Breadcrumb]:
        """Snapshot of the currently parked requests for the poll loop to check."""
        with self._lock:
            return list(self._crumbs.values())

    def _save(self) -> None:
        """Write the current set to the state file. Plain write — a crash mid-write is too rare to harden."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_bytes(_CRUMBS.dump_json(list(self._crumbs.values())))


def _read(path: Path) -> dict[str, Breadcrumb]:
    """Load + validate persisted breadcrumbs keyed by request_id; an absent file means none are parked."""
    if not path.exists():
        return {}
    crumbs = _CRUMBS.validate_json(path.read_bytes())
    return {crumb.request_id: crumb for crumb in crumbs}


_store: BreadcrumbStore | None = None
_store_lock = threading.Lock()


def get_store() -> BreadcrumbStore:
    """Return the process-wide breadcrumb store, built once from config on first use."""
    global _store
    if _store is None:
        with _store_lock:
            if _store is None:
                config = load_config()
                _store = BreadcrumbStore(config.state_path)
    return _store
