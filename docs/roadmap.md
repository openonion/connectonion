# Roadmap

What each version is for, and the order they come in. Progress is tracked on
[GitHub](https://github.com/openonion/connectonion/milestones).

There are no dates here, deliberately. [VERSIONING.md](../VERSIONING.md) is the
rule this follows: a version ships when its work has been run by somebody, not
when a date arrives. What this page gives you is the *order* and the *content* —
which is the part that can be committed to.

**Published stable:** 1.8.5 · **Current preview:** 1.8.6a5
(`pip install --pre connectonion`)

## 1.8.6 — WhatsApp groups, local models, mail windows, calendar invitations

Plan: [#1555](https://github.com/openonion/connectonion/issues/1555).
Five previews so far (a1–a5).

- **WhatsApp as an inbox provider**, connecting as a linked companion device
  because the Cloud API cannot join a group a human created ([#1543]). Accepted
  against a real account on 17 September; a2–a5 are almost entirely what that
  acceptance found.
- **Local models.** `model="ollama/…"` needs no key and no credits, and any
  other local runtime is reached with an explicit `base_url` ([#103], [#1538]).
- **Mail date windows and machine-readable output** — `--since` / `--until`,
  Outlook `--json` ([#1521], [#1522]).
- **Calendar invitations that reach people** ([#1547]).

## 1.8.7 — Personal Wiki

Design: [#1443](https://github.com/openonion/connectonion/issues/1443).
Implementation: [PR #1454](https://github.com/openonion/connectonion/pull/1454).

A notebook the assistant maintains from your sessions and mail. The AI is the
only writer in the MVP; organisation, updating and compaction live in Skills
under `connectonion/useful_skills/` rather than in bespoke code.

This is the version expected to take the longest, and that expectation is why
1.8.8 and 1.8.9 below are empty rather than pre-filled.

## 1.8.8 and 1.8.9 — deliberately unassigned

No plan is attached to either number, and that is the decision, not an omission.

Wiki is open-ended enough that anything scheduled behind it would be a date
nobody could keep. Patch numbers do not roll over, so these two are simply the
next two releases after 1.8.7 — whatever the work turns out to be, most likely
fixes found while Wiki is being built.

Work gets a number when somebody is about to do it.

## 1.9.0 — observable and replayable agent runs

The minor is cut when this is done being stabilised, per the rule in
VERSIONING.md. Two things are already assigned to it:

- **The agent notices things by itself** ([#1499]), the way Claude Code and
  Codex do: a watcher is *declared*, not wired up as a subprocess loop, and an
  inbox message, a file write and a timer all reach the agent the same way.
  This was previously scheduled as 1.8.9 and moved here, because being told
  that something happened and being able to replay what happened afterwards are
  the same story told from two ends.
- **A sender allowlist for chat principals** ([#1479]). Through 1.8.x the inbox
  is open by default — anyone who can @-mention the bot can command the agent,
  bounded only by platform scope. 1.9 applies the Host's existing trust levels
  to `<provider>:<sender>` principals in `.co/host.yaml`.

### Also tagged 1.9, not yet placed

Both name 1.9 as their target and neither is assigned to a patch inside it:

- [#1410] — learn user and project preferences from corrections (an RFC).
- [#1215] — a macOS-only `co-wechat` tool that drives the official WeChat client
  through Accessibility APIs. Its own text says *1.9 candidate*.

## 1.9.1 — the remaining mailbox adapters

Plan: [#1463](https://github.com/openonion/connectonion/issues/1463).

Telegram inbound ([PR #1400]), Discord ([PR #1433]) and the WhatsApp Cloud API
adapter ([PR #1434]) — all three already written against the mailbox core that
1.8.5 shipped, all three waiting.

In order: Telegram, then Discord, then WhatsApp. WhatsApp goes last because it
is the only one with a dependency outside this repository (`oo-api#227`, the
webhook inbox).

They wait until after 1.9.0 for one reason: each is a new `co <provider>` verb
surface, and the sender allowlist above changes who is allowed to use one. Adding
three more open doors and then fitting locks to all of them is more work than
fitting the lock first.

## Beyond 1.9

Not scheduled, in no particular order:

- secrets in the OS keychain rather than a plaintext `keys.env` ([#1497]);
- TrustAgent advising Auto Approve without becoming the security boundary
  ([#269]);
- secure agent-to-agent networking and relay transport;
- production deployment, health monitoring and environment management;
- stronger interactive debugging and time-travel inspection.

[#103]: https://github.com/openonion/connectonion/issues/103
[#269]: https://github.com/openonion/connectonion/issues/269
[#1215]: https://github.com/openonion/connectonion/issues/1215
[#1410]: https://github.com/openonion/connectonion/issues/1410
[#1479]: https://github.com/openonion/connectonion/issues/1479
[#1497]: https://github.com/openonion/connectonion/issues/1497
[#1499]: https://github.com/openonion/connectonion/issues/1499
[#1521]: https://github.com/openonion/connectonion/issues/1521
[#1522]: https://github.com/openonion/connectonion/issues/1522
[#1538]: https://github.com/openonion/connectonion/issues/1538
[#1543]: https://github.com/openonion/connectonion/pull/1543
[#1547]: https://github.com/openonion/connectonion/issues/1547
[PR #1400]: https://github.com/openonion/connectonion/pull/1400
[PR #1433]: https://github.com/openonion/connectonion/pull/1433
[PR #1434]: https://github.com/openonion/connectonion/pull/1434
