---
name: pumpup-inbox-batch
description: Use when the user wants to work through all the waiting runs of a Pump Up playbook in one go — answering every approval and information request under rules they set once, in parallel where possible. For a long local session; for one run at a time use the pumpup-inbox skill.
argument-hint: <playbook name>
---

Before anything else, check that the Pump Up tools (pumpup_*) are available. If they are not, stop and tell the user to connect Pump Up: open Customize > Plugins > Pump Up > Connectors, select Connect, sign in with their Pump Up account, then ask again. If they have no account, they can sign up at https://pumpup.com.

# Work a Pump Up playbook's inbox in a batch

Playbook: $ARGUMENTS

You answer every open request on this playbook's waiting runs under the user's standing rules. Every answer is
recorded in Pump Up under the user's name, resumes the hosted agent, and cannot be changed.

## 1. Set up

1. Find the playbook with pumpup_playbook_list; if no playbook was given or the name matches none or several,
   ask which. Read it with pumpup_playbook_get: its instructions are the standard for every decision.
2. Ask the user for their decision rules in one message: when to approve, when to reject, what to provide for
   common information requests, and what always goes back to them. Take "use the playbook's instructions" as a
   valid answer.
3. Confirm in plain words that the user authorizes you to answer requests inside these rules without asking
   each time. This standing confirmation is what lets you call pumpup_request_approve and
   pumpup_request_provide on their behalf. Without it, stop and use the pumpup-inbox skill instead.
4. Create `pumpup-inbox-batch-<playbook>-<date>.md` in the working directory and write the rules into it.

## 2. Work the runs

1. Call pumpup_run_list with status=WAITING and the playbookId.
2. Give each run to one sub-agent, in parallel, with the playbook instructions, the rules, and the steps below.
   Never give the same run to two sub-agents. Without sub-agents, work the runs one by one yourself.
3. For its run, a sub-agent:
   - calls pumpup_run_get, then pumpup_request_get for each open request, and reads the history with
     pumpup_run_event_list when the request alone does not show enough evidence;
   - answers each request that falls inside the rules: pumpup_request_approve for an approval,
     pumpup_request_provide for an information request;
   - leaves a request for the user when it is outside the rules, the evidence is thin, it needs a file, or
     pending is already false;
   - returns, per request: what was asked, the answer given or "left for you", and one line of reasoning.
4. Append each run's result to the log as it comes back: run name and link, then its requests and answers.
5. When the batch is done, call pumpup_run_list again: an answered run can come back with a new request, and new
   runs arrive. Skip any run whose open requests are all already logged as "left for you", and work the rest.
   Stop when no run is left to work, or the user stops you.

## 3. Hand back

Summarize: runs worked, answers given by kind, and the requests left for the user with their inbox links
(https://app.pumpup.com/inbox?session={runId}). Point out repeated patterns worth a playbook change, and offer the
pumpup-review-run skill for them.
