"""Upload workspace-relative files to Pump Up, confined to the agent's working directory.

Symlinks are resolved (realpath) on both the root and each path so a link inside the workspace
can't point the upload at a file outside it (a data-egress guard). Hermes file tools operate
relative to TERMINAL_CWD / cwd; attachments confine to the same root (override PUMPUP_WORKSPACE_DIR).
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Optional

from pumpup import AsyncPumpUp, Attachment


def _workspace_root() -> Path:
    """The directory agent-supplied attachment paths are resolved against and confined to."""
    raw = os.getenv("PUMPUP_WORKSPACE_DIR") or os.getenv("TERMINAL_CWD") or os.getcwd()
    return Path(os.path.realpath(raw))


async def upload_attachments(client: AsyncPumpUp, inputs: Optional[list[dict[str, Any]]]) -> list[Attachment]:
    """Upload each {path, label} and return task attachment refs; raises if a path escapes the workspace."""
    if not inputs:
        return []
    root = _workspace_root()
    refs: list[Attachment] = []
    for item in inputs:
        path = item["path"]
        abs_path = Path(os.path.realpath(root / path))
        if abs_path != root and root not in abs_path.parents:
            raise ValueError(f"pumpup: attachment path escapes the workspace: {path}")
        uploaded = await client.uploads.upload(file=(abs_path.name, abs_path.read_bytes()))
        refs.append(Attachment(upload_id=uploaded.id, label=item["label"]))
    return refs
