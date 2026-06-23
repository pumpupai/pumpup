import { failedTextResult } from "openclaw/plugin-sdk/agent-runtime";
import { formatErrorMessage } from "openclaw/plugin-sdk/error-runtime";

import { PumpUpError } from "@pumpupai/pumpup-sdk";

/// Structured failure surfaced on a tool result so the agent (and our logs) branch on the outcome
/// instead of seeing an opaque thrown error. `status: "failed"` is the runtime's failed-tool marker.
export type PumpUpToolFailure = {
  status: "failed";
  httpStatus: number | null;
  code: string | null;
  message: string;
};

/// Map any error raised while calling Pump Up into a structured, branchable tool failure (never throws).
export function toToolFailure(action: string, error: unknown) {
  if (error instanceof PumpUpError) {
    const httpStatus = error.statusCode ?? null;
    const body = describeBody(error.body);
    const message = body.message ?? formatErrorMessage(error);
    const tip = advice(httpStatus);
    const prefix = `${action} failed${httpStatus ? ` (HTTP ${httpStatus})` : ""}: ${message}.`;
    return failedTextResult(tip ? `${prefix} ${tip}` : prefix, { status: "failed", httpStatus, code: body.code, message });
  }
  const message = formatErrorMessage(error);
  return failedTextResult(`${action} failed: ${message}.`, { status: "failed", httpStatus: null, code: null, message });
}

/// Pull a human message (+ optional code) out of an SDK error body: `ApiError` (400) or `ErrorResponse`;
/// null message when the body carries neither (e.g. a connection/timeout error has no body).
function describeBody(body: unknown): { message: string | null; code: string | null } {
  if (body && typeof body === "object") {
    const fields = body as { message?: unknown; code?: unknown; error?: unknown };
    if (typeof fields.message === "string") {
      return { message: fields.message, code: typeof fields.code === "string" ? fields.code : null };
    }
    if (typeof fields.error === "string") {
      return { message: fields.error, code: null };
    }
  }
  return { message: null, code: null };
}

/// Short, status-specific guidance appended to the failure text so the agent knows whether to retry.
function advice(httpStatus: number | null): string {
  if (httpStatus === 400) {
    return "The request was invalid — fix the input and try again.";
  }
  if (httpStatus === 404) {
    return "The referenced project or task was not found — check the identifiers.";
  }
  if (httpStatus === 409) {
    return "This conflicts with the current state (it may already be decided) — do not retry unchanged.";
  }
  if (httpStatus !== null && httpStatus >= 500) {
    return "Pump Up had a server error; you may retry later.";
  }
  return "";
}
