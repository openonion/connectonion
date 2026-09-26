# Release channels

ConnectOnion has two release channels:

- **Stable** is the default `pip install connectonion` channel for production.
- **Preview** contains opt-in alpha, beta, and release-candidate builds.

Preview releases never replace the stable recommendation. Install one by
pinning its exact version: `pip install --upgrade 'connectonion==X.YbN'`. The
pin alone lets pip take that one preview. Do not add `--pre`: it applies to
every dependency too, and under it 1.8.8b7 resolved httpx 1.0.dev6, which has
no `AsyncClient`, and every remote agent call crashed.

## Current release

Stable **1.8.8** is the default production channel. See
[1.8.8 release notes](releases/1.8.8.md).

```bash
python -m pip install --upgrade 'connectonion==1.8.8'
```

## Current preview

Beta **1.8.9b9** was published with the Host watcher preview. That design is
being removed from subsequent source builds in favor of session-owned watches.
The b10 source tag has been prepared, but its package release is not yet
published. See the [b9 release notes](releases/1.8.9b9.md) for its historical
scope and [#1788](https://github.com/openonion/connectonion/issues/1788) for
the replacement.

```bash
python -m pip install --upgrade 'connectonion==1.8.9b9'
co --version
```

<details>
<summary>The preview line that became 1.8.5</summary>

Beta **1.8.5b11** made the command line name what to run next, and made
calendar invitations actually arrive. `co gcalendar` never passed Google's
`sendUpdates`, so an event with attendees invited nobody — and `Event created`
read the same whether three people were invited or none, so the silent failure
was indistinguishable from success until a client's guest said they got nothing.
Moving or cancelling a meeting told its attendees nothing either, which is worse.
The confirmation now names who was invited, and echoes the time in the zone it
was written in: `16:30+10:00` used to be confirmed as `06:30 AM`.

An audit against `useful_skills/cli-skill-design` fixed four things in the CLI
itself. Every deliberate refusal printed two next steps, one of them useless and
read first by anyone merging streams. A typo ended at `co --help` even when
Click had already worked out the answer — `co larc` now says `Next: co lark`,
and `co like`, which nothing matches, says `Next: co commands` rather than
pointing at a boxed screen of groups. Two failures named no command at all. And
the `co env` skill had never learned about `rotate`, `--secret` or
`--from-console`.

A missing bot permission is now one link away instead of a Developer Console
visit, and #1462's reconnect gate passed: history recovery had never once been
allowed to run, and once it was, a message posted during a 90-second gap came
back exactly once.

It carries `b10`, which makes `co auth lark` create an application and return its
secret — **correcting b9, which shipped a warning saying it could not.** The
cause was one path segment. We printed the URL the SDK hands over,
`<open-host>/page/launcher?user_code=…`, and that page renders "Link expired"
whenever its own acknowledgement call fails, for a code the server reports as
pending in the same second. `lark-cli` discards that URL and builds
`<open-host>/page/cli?user_code=…`; pointed there, the same tenant produced the
creation form, an application, and its secret. Nothing about a tenant, a region,
or a code's lifetime was ever involved. `--app-id` reuse works too.

It carries `b9`, which lets an app secret be stored encrypted. `co env set --secret`
writes ciphertext under a key derived at a SLIP-0013 path and kept nowhere, and
`co env rotate` moves it to the next index. There is no master key, so there is
no keychain to be blocked by a sandbox or a machine with no logged-in human; the
root is `.co/keys/agent.key`, not the optional `recovery.txt`, so writing your
twelve words down and deleting that file cannot orphan a secret — and those
words still reach it, because the agent key is derived from them.

It also carries `co env set --from-console`, which accepts an app credential
copied from the Developer Console — still the right route when you already keep
an application there, though no longer the only way out of a tenant `co auth`
could not serve. And `co auth lark` reports the server's real link lifetime
instead of the SDK's fallback of 600, which is how "it expired after two
minutes" was investigated as a timeout that never existed.

It carries `b8`, which makes `co auth lark` begin on Lark. It used to print an
`open.feishu.cn` link and, on failure, tell a Lark user to run `co auth feishu`;
the accounts domain, the wording, and the reuse command offered from lark-cli's
config all follow the brand now.

It carries `b7`, which lets an agent reach a tab the site opened for itself — a
payment popup, a "view invoice" button, any `target="_blank"` link. Those pages
belong to no session, so they appeared on no board and every `-t` command kept
running in the page before them. `co browser list_pages` shows the browser's
real pages with the session driving each, `switch_page <index>` points a session
at one, and `tab ls` counts what it cannot show and names the verb.

It carries `b6`, which installs the paid browser's driver from PyPI. `onionwright`
held only a name reservation there — one file and a version string — while the
real client travelled a licence-gated endpoint; it is published normally now, so
`pip install 'connectonion[wtf]'` works and the installer is 289 lines shorter.
The browser binary stays licence-gated and the runtime licence is still checked
at launch.

It carries `b5`, which makes asking for the paid engine enough. The route to the WTF
Browser was three commands, and the first one asked the caller to decide nothing —
the engine cannot run without its client. An explicit `--engine wtf` now fetches
it; `auto`, `system` and `--engine wtf help` still install nothing, because
importing ConnectOnion or taking the free engine must never mutate a Python
environment. The paid browser also runs on **Intel Macs** now: its object had
been staged and unpromoted since a gate failure on 2026-09-04, and the re-run
passed on real Intel hardware on 2026-09-13.

It carries `b4`, which fixes what `b3` could not install. `co browser install-onion`
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

The no-loss-across-a-reconnect gate passed on 15 September, against a real
group — the last thing between this line and stable.
See [1.8.5b11 release notes](releases/1.8.5b11.md).

</details>

All eleven 1.8.5 previews (a1 through b11) are superseded by stable 1.8.5;
1.8.4a1 and 1.8.4a2
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
python -m pip install connectonion==1.7.0a13
```

## Design Journal

Release notes record what changed. A Design Journal post records the problem,
alternatives, decision, tradeoffs, evidence, and what would make us revisit it.
Meaningful feature-train launches, phase promotions, stable releases, and
material architecture decisions receive a new or substantially updated post.

The OIP-only decision is recorded in
[DD-053](design-decisions/053-oip-only-browser-and-native-coding-adapters.md).
