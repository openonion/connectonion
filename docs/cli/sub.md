# co sub - Subscribe to Published Agents

Follow another agent's address, mirror their published skills to your machine, and make them available to every coding agent on your system (Claude Code, Codex, OpenClaw, Cursor, Kiro).

For agent-readable subscription guidance, `co copy oo-subscribe` copies the
bundled skill into the current project's `.co/skills/` directory.

## Quick Start

```bash
# Subscribe to a publisher (use the full 0x address — see "Address vs alias" below)
co sub sync 0xcd92510bb6cc090374ecc345ef8c19b9d3797624fd1fbf7e078a9372fc31bdc1

# Re-sync every publisher you follow (refresh after they push new versions)
co sub

# Show who you follow (local only, no relay calls)
co sub list

# Stop following
co sub remove changxing
```

Restart a coding agent only when the sync output reports that it installed
skills into that agent. A recorded subscription with zero mirrored or installed
skills needs no restart.

## Why

`co announce` lets someone publish their `~/.co/agent.json`, public SKILL.md bodies and companion files to the relay. `co sub` is the other half: pull a publisher's skills into your local environment and route them into the coding agents you actually use.

The model is a flat relationship record:

```
~/.co/subscriptions.txt           ← "who do I follow"        (the relationship)
~/.co/subscription-state/<address>.json ← highest authenticated revision (rollback guard)
~/.co/subs/<alias>/agent.json     ← "what do I have"         (mirrored profile)
~/.co/subs/<alias>/skills/<name>/ ← "their actual skills"    (body and signed companion files)
~/.<tool>/...                     ← "where my agent sees them" (fan-out)
```

Subscriptions are stored one `<address> <local alias>` per line. The address is the publisher identity. The alias is pinned on first subscription, so a publisher rename does not strand old installations; `co sub list` shows the new signed alias beside it.

## How the fan-out works

One subscription is mirrored once and then distributed into every coding agent that's installed on your machine:

```
relay
  ↓  (1x GET profile, NxGET skill body)
~/.co/subs/alice/                  ← single source of truth
  ↓  fanout.install_all()
~/.claude/plugins/alice/           → symlink to the bundle (whole-bundle plugin)
~/.codex/skills/alice-tweet/       → per-skill symlink
~/.codex/skills/alice-post/        → per-skill symlink
~/.openclaw/skills/alice-tweet/    → per-skill symlink
~/.cursor/rules/alice-tweet.mdc    → file copy with frontmatter rewritten
~/.kiro/steering/alice-tweet.md    → plain file copy
```

Per-tool behavior:

| Tool | Destination | Mechanism |
|------|-------------|-----------|
| Claude Code | `~/.claude/plugins/<alias>/` | Symlink to the whole bundle |
| Codex | `~/.codex/skills/<alias>-<skill>/` | Per-skill symlinks |
| OpenClaw | `~/.openclaw/skills/<alias>-<skill>/` | Per-skill symlinks |
| Cursor | `~/.cursor/rules/<alias>-<skill>.mdc` | File copy with `alwaysApply: false` frontmatter |
| Kiro | `~/.kiro/steering/<alias>-<skill>.md` | Plain file copy |

Only tools that exist on your machine (have a `~/.<tool>/` directory) are touched.

## Commands

`co sub sync <target>` follows or refreshes one publisher. Bare `co sub`
refreshes every entry in `~/.co/subscriptions.txt`; it does not accept a target.
`list` and `remove` are separate subcommands.

### `co sub sync <0xaddress>` — sync one publisher

Resolve the profile, mirror the bundle, append to `~/.co/subscriptions.txt`, and fan out.

```bash
co sub sync 0xcd92510bb6cc090374ecc345ef8c19b9d3797624fd1fbf7e078a9372fc31bdc1
```

**Output:**
```
Fetching profile 0xcd92510bb6cc...
✓ Subscribed to changxing (0xcd92510bb6cc...)
  mirrored 18 skill(s) → /Users/you/.co/subs/changxing
  claude: installed 18 skill(s)
  codex: installed 18 skill(s)
  openclaw: installed 18 skill(s)
  cursor: installed 17 skill(s)

→ Restart your coding agent to load the new skills.
```

Re-running reconciles the installed set with the signed publish. Removed or withheld bodies are removed from the mirror and from owned coding-agent installations. A new mirror is staged before replacing the previous one; a staging failure leaves the old mirror available.

Read the mirrored and installed counts in the result. `Subscribed to` means
the relationship was recorded, even when the publisher withheld every body or
no coding agent was detected. Only a positive installed count calls for a
restart. `co sub list` reports listed/mirrored counts. The first includes withheld
bodies; the second counts SKILL.md files available locally. Installation conflicts
are reported at sync time and leave the user's existing path alone. `co ai`
reads active subscriptions under `<local-alias>-<skill>`.

Once a publisher is in `~/.co/subscriptions.txt`, you can use the alias as a shorthand for refresh: `co sub sync changxing` does the same thing.

**Options:**

| Option | Description |
|--------|-------------|
| `--relay <url>` | Override the configured backend for this sync |

### `co sub` — sync every subscription

With no subcommand, walks `~/.co/subscriptions.txt` and re-syncs each publisher in order.

```bash
co sub
```

If a publisher is unreachable the command stops at the failure — re-run after fixing the underlying issue. (Fail-fast is intentional: tolerating mid-loop failures hides real problems. Revisit if anyone hits this with many subscriptions.)

Cost-wise, each subscription costs `1 + N_skills` HTTP requests against the relay (1 profile + 1 per skill body). For 5 publishers with ~20 skills each that's ~100 requests — tolerable but not cheap. A future `profile-head` endpoint on the relay will let `co sub` skip publishers whose version hasn't changed; the CLI surface won't change when that lands.

### `co sub list` — local view only

Read `~/.co/subscriptions.txt` and the local bundle to show version and listed/mirrored skill counts. No relay calls.

```bash
co sub list
```

**Output:**
```
                              Subscriptions
┏━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━┳━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━┓
┃ Alias     ┃ Address            ┃ Version ┃ Listed/Mirrored ┃ Installed ┃
┡━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━╇━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━┩
│ changxing │ 0xcd92510bb6cc…  │ v0.1.0  │           18/18 │ codex:18  │
└───────────┴────────────────────┴─────────┴─────────────────┴───────────┘

Stored in: /Users/you/.co/subscriptions.txt
```

No network calls. Pure local read.

### `co sub remove <alias|0xaddress>`

Reverse of `sync`: drop the line from `~/.co/subscriptions.txt`, uninstall every per-tool symlink/copy, and delete `~/.co/subs/<alias>/`.

```bash
co sub remove changxing
# or
co sub remove 0xcd92510bb6cc090374ecc345ef8c19b9d3797624fd1fbf7e078a9372fc31bdc1
```

Idempotent — removing something you haven't subscribed to prints `Not subscribed to '<target>'` and exits cleanly.

## The subscriptions file

`~/.co/subscriptions.txt` is plain text. Let `co sub sync` and `co sub remove`
maintain it so the saved address, mirrored bundle, installed copies, and
rollback watermark stay consistent.

```
# ~/.co/subscriptions.txt — agents you follow
# Format: <address> <alias>
# Managed by `co sub`. Re-run `co sub sync <address>` to refresh one.
0xcd92510bb6cc090374ecc345ef8c19b9d3797624fd1fbf7e078a9372fc31bdc1 changxing
```

The mirrored bodies live separately at `~/.co/subs/<alias>/` — version and skill count are read from `<alias>/agent.json`, not from this list.

## Address vs alias

**First-time subscriptions require a 0x address.** Aliases are mutable: a publisher can change their alias, the relay can serve the wrong agent under a familiar name, and there's no way for the subscriber to tell after the fact. Subscribing by alias would be an MITM hole.

Once you've subscribed by address, that day's alias is pinned locally next to the address. Later publisher alias changes appear in `co sub list`; the pinned local alias remains a shortcut for refresh:

```bash
co sub sync changxing             # works once "changxing" is in subscriptions.txt — refreshes
co sub remove changxing      # works the same way
```

If you type a bare alias that's *not* already in `subscriptions.txt`, `co sub` errors out and tells you to paste the address. There is no alias→address resolution against the relay.

## Refreshing

`co sub` IS the refresh — there's no separate "check then maybe pull" step. Subscribing and refreshing are the same operation. To pick up updates:

```bash
co sub                         # refresh everything
co sub sync changxing               # refresh one (alias works once pinned)
co sub sync 0xcd92510bb6cc...       # refresh one (explicit address)
```

Each re-run re-fetches the profile, re-writes the mirrored bodies, and re-runs the fan-out. The subscriptions.txt line is deduplicated.

A lazy-check mode that only pulls bodies when the relay reports a newer version is the planned v2 — it needs a `profile-head` endpoint on the relay first. The CLI surface won't change.

## Authenticity and rollback protection

Before writing, `co sub sync` fetches every public skill body, reconstructs the
publisher's complete profile, and verifies its Ed25519 `profile-v2` signature
against the canonical lowercase 0x address you pinned. The signed profile
contains `attestation_version: profile-v2` and a positive 64-bit `revision`.
The version marker is itself signed, so a relay cannot relabel a v1 proof as
v2. The subscriber stores the highest
accepted revision outside the mirrored bundle:

- a lower revision is a rollback and is refused;
- the same revision with a different signature is equivocation and is refused;
- the same revision and signature is an idempotent retry;
- a higher valid revision advances the watermark before the content is exposed.

A relay-modified alias, skill list, body, revision, or signature is refused.
Unsigned and `profile-v1` profiles remain visible in discovery but cannot be
installed; their publisher must re-announce with ConnectOnion 1.6.0.

The first install is trust-on-first-valid-revision: with no local watermark,
the subscriber can only authenticate what it receives, not know whether the
relay withheld a newer historical publish. Preserve
`~/.co/subscription-state/` in backups. Losing it loses rollback memory; restore
it or verify the current revision out of band before syncing again. `co sub
remove` deliberately retains the watermark so unsubscribe/resubscribe cannot
be used to erase history.

A publisher who intentionally wants old content publishes that content again
at a new, higher revision. A key rotation creates a new 0x address and therefore
a new history; subscribers must explicitly subscribe to it. Publishers using
the same key on multiple devices must keep clocks synchronized and carry the
latest `~/.co/profile-publish-state/<address>.json`; the backend refuses a
device whose revision does not advance the stored authenticated revision.

Every `co sub` still pulls the full profile and every public body even when
nothing changed. A future `profile-head` endpoint can make that incremental
without changing the rollback rule or CLI.


## Files touched

```
~/.co/subscriptions.txt              ← appended/rewritten on add/remove
~/.co/subscription-state/<address>.json ← retained monotonic rollback watermark
~/.co/subs/<alias>/agent.json        ← mirrored publisher profile
~/.co/subs/<alias>/skills/<name>/SKILL.md  ← mirrored skill body
~/.co/subs/<alias>/skills/<name>/*         ← signed companion files
~/.co/subscription-installs/<alias>.json  ← local installation ownership
~/.claude/plugins/<alias>/           ← symlink (whole bundle)
~/.codex/skills/<alias>-<skill>/     ← per-skill symlinks
~/.openclaw/skills/<alias>-<skill>/  ← per-skill symlinks
~/.cursor/rules/<alias>-<skill>.mdc  ← file copy (frontmatter rewritten)
~/.kiro/steering/<alias>-<skill>.md  ← plain file copy
```

## See also

- [co announce](../network/protocol/announce-message.md) — the publisher side: sign `agent.json` and push to the relay
- [co setup](setup.md) — set up `~/.co/` identity and skill library
- [co skills](skills.md) — discover and import skills you've written yourself
- [Multi-Agent Networking](../network/README.md) — the broader relay/host/connect picture
