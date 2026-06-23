# Pump Up × OpenClaw plugin

Lets an OpenClaw agent request a human approval/elicitation from [Pump Up](https://pumpup.com), durably
park the wait as a TaskFlow, and resume agent work when the decision arrives. Design: this repo's
`tech-docs/current/openclaw-plugin.md`.

## Build

```
npm install        # resolves pumpup-sdk (git dep on pumpup-sdk-typescript#dev, built on install)
npm run build      # tsc → dist/
npm run typecheck  # tsc --noEmit
```

The plugin depends on the Pump Up TypeScript SDK as a git dependency on the SDK repo's `dev` branch
(like the Hermes plugin); `npm install` builds it on install via the package's `prepare` script. Swaps
to the published `pumpup-sdk` on npm later (see this repo's `tech-docs/current/sdks.md`).

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
