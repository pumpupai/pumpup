import type { OpenClawPluginApi } from "openclaw/plugin-sdk/plugin-entry";

/// Validated Pump Up plugin config, read from `plugins.entries.pumpup.config`.
/// `apiKey` stays opaque (a SecretInput — literal string or SecretRef) and is resolved in `client.ts`.
export type PumpUpPluginConfig = {
  baseUrl: string;
  apiKey?: unknown;
  ownerSessionKey: string;
  pollIntervalMs: number;
  maxConcurrentResumes: number;
};

/// Read + shape the plugin config; the two required string fields fail loudly when absent
/// (a missing value is a deploy mistake, not a runtime state to handle).
export function readConfig(api: OpenClawPluginApi): PumpUpPluginConfig {
  const raw = (api.pluginConfig ?? {}) as Record<string, unknown>;
  const baseUrl = reqString(raw.baseUrl, "baseUrl");
  const ownerSessionKey = reqString(raw.ownerSessionKey, "ownerSessionKey");
  const pollIntervalMs = typeof raw.pollIntervalMs === "number" ? raw.pollIntervalMs : 10_000;
  const maxConcurrentResumes = typeof raw.maxConcurrentResumes === "number" ? raw.maxConcurrentResumes : 4;
  return { baseUrl, apiKey: raw.apiKey, ownerSessionKey, pollIntervalMs, maxConcurrentResumes };
}

/// Require a non-empty string config value, throwing a clear operator-facing error otherwise.
function reqString(value: unknown, key: string): string {
  if (typeof value === "string" && value.length > 0) {
    return value;
  }
  throw new Error(`pumpup: config '${key}' is required (set plugins.entries.pumpup.config.${key})`);
}
