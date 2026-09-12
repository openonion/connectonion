# Release channels

ConnectOnion has two release channels:

- **Stable** is the default `pip install connectonion` channel for production.
- **Preview** contains opt-in alpha, beta, and release-candidate builds.

Preview releases never replace the stable recommendation. Install one with
`--pre` or pin its exact version.

## Current release

Stable **1.8.4** brings explicit global configuration, `co env`, reviewed Gmail
operations, verified Synology sharing and Outlook calendar commands. See
[1.8.4 release notes](releases/1.8.4.md) for migration and acceptance limits.

```bash
python -m pip install --upgrade connectonion==1.8.4
co --version
co env
```

## Current preview

Beta **1.8.5b4** fixes what `b3` could not install. `co browser install-onion`
reported `pip could not install Onionwright (exit 1)` when pip had declined by
policy — PEP 668's externally-managed marker, the default on Homebrew and most
distro Pythons — and had named the override itself. pip's output is captured now
so a refusal can be told from a failure, and a policy refusal names the
interpreter and both routes out. The new `--break-system-packages` is opt-in.

It carries everything from `b3`, which fixes two ways the browser could waste an afternoon, both
found by an unattended agent. `co browser wait` takes seconds while every
neighbouring knob is named in milliseconds, so `wait 2500` meant forty-one
minutes holding a tab's lock — every command behind it timed out while
`status` kept answering, so nothing looked broken. It is capped at 60 seconds
now and refuses before taking the lock, naming the value you meant. And a
daemon pinned to an engine refused every bare command, `close` included, while
its own error told you to run `close`: `auto` is no preference now, verbs that
touch no page are never gated, and a refusal names only commands that daemon
would accept. A dead paid session names its recovery, and the paid engine says
it bills before it spends.

It carries everything from `b2`: `co browser config`, the paid engine called
`wtf`, `consume`, and `co auth feishu --app-id`.

It is a beta because the no-loss-across-a-reconnect gate has not passed: the
repair is offline-tested and has not been run against a real group. The release
notes list what else to decide before putting it on a machine other people use.
See [1.8.5b4 release notes](releases/1.8.5b4.md).

```bash
python -m pip install --pre connectonion==1.8.5b4
co --version
```

The 1.8.5a1, 1.8.5a2, 1.8.5b1, 1.8.5b2 and 1.8.5b3 previews are superseded; 1.8.4a1 and 1.8.4a2
are historical, and the planned 1.8.4b1 was folded into the stable release. The
tag workflow builds and verifies the public package before documentation is
deployed. Google authorization from 1.8.3 is retained; TikTok remains deferred.
The sections below are historical notes.

## Historical 1.7 preview work

- Stable release: `1.6.10`
- Preview target: `1.7.0a13`
- Browser client: `@connectonion/react@0.4.2-alpha.11`

The preview uses OIP 0.1 as the only first-party browser protocol. The Python
Host serves the authenticated `/ws` connection; `@connectonion/react` owns the
browser client; O Chat consumes the exact React prerelease. Codex and Claude
Code remain native backend provider adapters and publish their normalized
activity through OIP.

Alpha 7 makes explicit Codex requests deterministic: natural-language verbs,
`/codex`, delegation language, and Chinese requests route through the native
Codex adapter before the model chooses a tool. `open Codex` creates or resumes
the provider session without inventing a prompt, and an OIP-visible guard blocks
direct Codex launches through shell tools without affecting ordinary shell text.
The browser continues to use OIP 0.1 and the same shared Work Room card.

Alpha 8 closes the open-only lifecycle found by public browser acceptance.
Codex writes a rollout only after its first turn, so an open-only app-server now
stays alive in a bounded, expiring registry. The first Work Room message claims
that exact provider thread, completes the real turn, persists the rollout, and
then closes the process. The session ID shown when Codex opens is therefore the
same one used by the first task.

Alpha 9 makes reload an authenticated OIP reattach instead of a false second
login. A fresh signed CONNECT that reaches the still-live relay queue is accepted
only when caller, recipient, signed-command capability, OIP protocol, and session
are unchanged. The Host republishes CONNECTED without duplicating a running
forwarder; every mismatch and signature replay remains rejected.

Alpha 10 separates that reattach proof from first-connect authorization. The
same live caller must still present a fresh signature and unchanged recipient,
capability, protocol, session, replay claim, and current blacklist status, but
the Host no longer repeats mutable onboarding/contact/admin policy or rebuilds
permission authority for a connection that is already authorized. It republishes
the existing mode, profile, transcript, and dashboard state. A first Send or
Codex Work Room follow-up racing the eager browser CONNECT now reaches its input
instead of surfacing a local trust-file error.

Alpha 11 makes the OIP 0.1 rolling window explicit. Descriptor-less 0.1 peers
remain readable, Direct and Relay use the same compatibility gate, unsupported
versions fail once without retry, discovery stays uncached, and Host records only
content-free compatibility classifications. DD-053 now defines the release and
time boundary before a reader can be removed.

Alpha 12 closes the production blockers found by real Chrome acceptance. Claude
Code keeps its authenticated macOS CLI environment and publishes a resumable
Work Room lifecycle like Codex. Stop now terminates the complete hosted Bash
process group, and multimodal messages no longer crash slash-command dispatch or
lose their image parts. The release gate includes fresh onboarding, approval,
cancellation with a process-tree check, text and image attachments, reconnect,
both native coding adapters, mobile layout, and session rollback across exact
published React and Host prereleases.

Alpha 13 makes a long native coding run observable while it is still running.
Codex and Claude Code emit their provider lifecycle and child work in a live,
non-persistent presentation lane; their canonical trace remains transactional
until the outer hosted tool commits. A cancellation closes the live provider
card without leaking that uncommitted trace. Native Codex approvals now carry
safe exact provider correlation, so React and O Chat put the decision on the
right Work Room card instead of a generic outer tool. The default UI presents a
bounded semantic activity snapshot; raw commands and outputs stay behind
disclosure.

Normal upgrades stay on stable. Preview testers opt in explicitly:

```bash
python -m pip install --pre --upgrade connectonion
python -m pip install connectonion==1.7.0a13
```

## Design Journal

Release notes record what changed. A Design Journal post records the problem,
alternatives, decision, tradeoffs, evidence, and what would make us revisit it.
Meaningful feature-train launches, phase promotions, stable releases, and
material architecture decisions receive a new or substantially updated post.

The OIP-only decision is recorded in
[DD-053](design-decisions/053-oip-only-browser-and-native-coding-adapters.md).
