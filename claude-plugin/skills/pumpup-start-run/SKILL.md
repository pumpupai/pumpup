---
name: pumpup-start-run
description: Use when the user wants to start a Pump Up run — launch one real case on a playbook for the hosted agent to work.
---

Before anything else, check that the Pump Up tools (pumpup_*) are available. If they are not, stop and tell the user to connect Pump Up in their assistant, sign in with their Pump Up account, then ask again. Give the steps for the assistant you are running in — in Claude: Customize > Plugins > Pump Up > Connectors, then Connect; elsewhere, the connector or app settings of the Pump Up plugin. If they have no account, they can sign up at https://pumpup.com.

# Start a Pump Up run

1. Call pumpup_playbook_list and help the user pick the playbook. Skip archived ones.
2. Call pumpup_playbook_get and read its instructions to see what case input it needs. Ask the user for the real case fields, one question at a time, and a short run name. Ask whether this run needs any extra steering on top of the playbook; if so, send it as run_instructions.
3. Show the playbook, the run name and the metadata you will send, and wait for the user's yes. Metadata is the agent's verbatim case input: real fields only, never test expectations or hints.
4. Call pumpup_run_create with metadataPatch.set holding those fields. The run is real: the agent starts acting on it.
5. Give the run link and offer to fetch its progress with pumpup_run_get.
