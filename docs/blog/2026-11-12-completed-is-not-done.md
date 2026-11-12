---
description: In hosted Auto mode, Codex refused every file write and command, and the card still said Completed. Hosted Auto now runs inside the workspace sandbox, and any refused action marks the run blocked.
tags: [Codex, Host, Approvals]
---

# Completed is not done

In O Chat, in Auto mode, we asked the agent to use Codex to create a few files and run the tests. Codex's own answer said that file creation and command execution had been rejected. Nothing was created. The card above it showed a green check: **Codex · Completed — Completed the provider run after the recorded test checks**. Nobody was ever asked to approve anything.

We saw the same thing on a Mac Host, a Linux Host, and in both remote directions. Running `codex exec -s workspace-write` by hand on the same machine worked fine. So Codex was capable of the work; something between O Chat and Codex was refusing it and then calling the result a success.

## Three small mistakes in a row

First, hosted Auto mapped Codex to our `manual` approval mode, which becomes Codex's `approvalPolicy=untrusted`. Under that policy Codex asks before every write, even inside the workspace. When the person asking was a contact rather than an admin, or the session had no approval UI, the approval gate said no before any card was drawn. Auto mode quietly meant "ask, then refuse".

Second, Codex marks a refused action as `status=declined`, with no exit code. Our event converter only treated `failed`, `error` or a non-zero exit code as a failure, so a declined action showed as Completed. A declined `pytest` even counted as a "recorded test check" in the summary.

Third, a native turn that finished returned exit code 0, even if every action in it had been declined.

Each step was reasonable alone. Together they turned "nothing happened" into a green check.

## The fix

Hosted Auto now runs Codex in the workspace-write sandbox with `approvalPolicy=never`, for new and resumed threads. Work inside the workspace goes ahead without asking; a request to leave it is still refused. The explicit "Ask for approval", Read only and Full access modes keep their own boundaries.

Any declined item or refused approval now marks the run **blocked**: the envelope says `status=blocked`, `exit_code=1` and a `blocked_reason` such as `admin_required` or `approval_ui_unavailable`, and the card ends as failed with a "Blocked: …" summary instead of Completed.

There was also a product question: should a contact's Auto run be allowed at all? We chose context over control. The run is allowed, recorded once per run in the approvals log (`co approvals`), announced to the requester once per session, and reported to the operator together with the command to revoke that requester.

Codex is now also found at `~/.local/bin/codex`, where its installer puts it and where a background service's PATH does not look.

## How we checked

`tests/unit/test_codex_refusals.py` drives the real app-server client against a fake server: a first turn and a resume, a contact requester, a missing approval UI, an explicit deny, an approval UI that raises, and a decline with no callback at all. On main those tests fail, and with the fix they pass.

The lesson: a status word has to come from what actually happened, not from the fact that the process exited. "The turn ended" and "the work was done" are different claims.
