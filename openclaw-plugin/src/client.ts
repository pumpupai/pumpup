import type { OpenClawConfig } from "openclaw/plugin-sdk/plugin-entry";
import { coerceSecretRef, resolveSecretRefValues } from "openclaw/plugin-sdk/secret-ref-runtime";

import { PumpUpClient } from "@pumpupai/pumpup-sdk";
import type { PumpUpPluginConfig } from "./config.js";

/// Build the Pump Up SDK client. `apiKey` is a lazy async Supplier so SecretRef resolution
/// happens per-request, not at plugin load; absent config falls back to the SDK's PUMPUP_API_KEY env.
export function buildClient(cfg: PumpUpPluginConfig, openclawConfig: OpenClawConfig): PumpUpClient {
  const options: PumpUpClient.Options = { baseUrl: cfg.baseUrl };
  if (cfg.apiKey != null) {
    options.apiKey = () => resolveApiKey(cfg.apiKey, openclawConfig);
  }
  return new PumpUpClient(options);
}

/// Resolve the configured apiKey to a literal: a plain string passes through, a SecretRef
/// resolves through the host's configured secret providers.
async function resolveApiKey(apiKey: unknown, config: OpenClawConfig): Promise<string> {
  const ref = coerceSecretRef(apiKey, config.secrets?.defaults);
  if (!ref) {
    if (typeof apiKey === "string") {
      return apiKey;
    }
    throw new Error("pumpup: config 'apiKey' must be a string or SecretRef");
  }
  const resolved = await resolveSecretRefValues([ref], { config, env: process.env });
  const value = [...resolved.values()][0];
  if (typeof value !== "string") {
    throw new Error(`pumpup: could not resolve apiKey SecretRef (${ref.source}:${ref.id})`);
  }
  return value;
}
