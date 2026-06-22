"""Attachment upload confinement — the data-egress guard. A path (or symlink) that resolves outside the
workspace must be rejected before any upload."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from pumpup import Attachment
from pumpup_hermes.attachments import upload_attachments


async def test_relative_path_escaping_workspace_is_rejected(tmp_path, monkeypatch):
    workspace = tmp_path / "ws"
    workspace.mkdir()
    (tmp_path / "secret.txt").write_text("top secret")
    monkeypatch.setenv("PUMPUP_WORKSPACE_DIR", str(workspace))
    client = MagicMock()
    client.uploads.upload = AsyncMock()
    with pytest.raises(ValueError, match="escapes the workspace"):
        await upload_attachments(client, [{"path": "../secret.txt", "label": "L"}])
    client.uploads.upload.assert_not_awaited()


async def test_symlink_escaping_workspace_is_rejected(tmp_path, monkeypatch):
    workspace = tmp_path / "ws"
    workspace.mkdir()
    secret = tmp_path / "secret.txt"
    secret.write_text("top secret")
    (workspace / "link").symlink_to(secret)  # a link inside the workspace pointing out
    monkeypatch.setenv("PUMPUP_WORKSPACE_DIR", str(workspace))
    client = MagicMock()
    client.uploads.upload = AsyncMock()
    with pytest.raises(ValueError, match="escapes the workspace"):
        await upload_attachments(client, [{"path": "link", "label": "L"}])
    client.uploads.upload.assert_not_awaited()


async def test_in_workspace_file_uploads(tmp_path, monkeypatch):
    workspace = tmp_path / "ws"
    workspace.mkdir()
    (workspace / "f.txt").write_text("hello")
    monkeypatch.setenv("PUMPUP_WORKSPACE_DIR", str(workspace))
    client = MagicMock()
    client.uploads.upload = AsyncMock(return_value=MagicMock(id="up1"))
    refs = await upload_attachments(client, [{"path": "f.txt", "label": "Doc"}])
    assert refs == [Attachment(upload_id="up1", label="Doc")]
    client.uploads.upload.assert_awaited_once()
