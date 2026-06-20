import { realpath } from "node:fs/promises";
import { basename, resolve, sep } from "node:path";

import type { PumpUp, PumpUpClient } from "../../../sdks/typescript/index.js";

/// One agent-supplied attachment: a workspace-relative file path + display label.
export type AttachmentInput = { path: string; label: string };

/// Upload workspace-relative files to Pump Up and return task attachment refs. Paths are confined to
/// the agent workspace (data-egress guard); a failed upload propagates for structured error mapping.
export async function uploadAttachments(
  client: PumpUpClient,
  workspaceDir: string | undefined,
  inputs: AttachmentInput[] | undefined,
): Promise<PumpUp.Attachment[]> {
  if (!inputs || inputs.length === 0) {
    return [];
  }
  if (!workspaceDir) {
    throw new Error("pumpup: attachments require an agent workspace directory");
  }
  // realpath both sides so a symlink inside the workspace can't point the upload at a file outside it.
  const root = await realpath(resolve(workspaceDir));
  const refs: PumpUp.Attachment[] = [];
  for (const input of inputs) {
    const abs = await realpath(resolve(root, input.path));
    if (abs !== root && !abs.startsWith(root + sep)) {
      throw new Error(`pumpup: attachment path escapes the workspace: ${input.path}`);
    }
    const uploaded = await client.uploads.upload({ file: { path: abs, filename: basename(abs) } });
    refs.push({ uploadId: uploaded.id, label: input.label });
  }
  return refs;
}
