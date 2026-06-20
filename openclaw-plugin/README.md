# Pump Up × OpenClaw plugin

Lets an OpenClaw agent request a human approval/elicitation from [Pump Up](https://pumpup.com), durably
park the wait as a TaskFlow, and resume agent work when the decision arrives. Design: this repo's
`tech-docs/current/openclaw-plugin.md`.

## Build

```
npm install
npm run build      # tsup → dist/index.js (bundles the local Pump Up SDK; openclaw stays external)
npm run typecheck  # tsc --noEmit
```

The plugin bundles the local Fern SDK source at `../../sdks/typescript` (see this repo's
`tech-docs/current/sdks.md`). Swapping to the published `pumpup-sdk` later is an import change.

## Install (dev gateway)

```
openclaw plugins install <abs path to this dir>
```

## Config (`plugins.entries.pumpup.config`)

| Key | Required | Notes |
|---|---|---|
| `baseUrl` | yes | Pump Up agent API base URL |
| `apiKey` | no | Literal or SecretRef; falls back to `PUMPUP_API_KEY` env |
| `ownerSessionKey` | yes | Stable sessionKey owning all Pump Up flows |
| `pollIntervalMs` | no | Decision poll interval (default 10000) |
| `maxConcurrentResumes` | no | Resume fan-out cap per tick (default 4) |
