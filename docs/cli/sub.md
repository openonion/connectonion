# co sub - Subscribe to Published Agents

Follow another agent's address, mirror their published skills to your machine, and make them available to every coding agent on your system (Claude Code, Codex, OpenClaw, Cursor, Kiro).

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

After any `co sub` invocation that pulls new content, **restart your coding agent** to pick up the new skills.

## Why

`co announce` lets someone publish their `~/.co/agent.json` + skill bodies to the relay. `co sub` is the other half: pull a publisher's skills into your local environment and route them into the coding agents you actually use.

The model is a flat relationship record:

```
~/.co/subscriptions.txt           ← "who do I follow"        (the relationship)
~/.co/subs/<alias>/agent.json     ← "what do I have"         (mirrored profile)
~/.co/subs/<alias>/skills/<name>/ ← "their actual skills"    (mirrored bodies)
~/.<tool>/...                     ← "where my agent sees them" (fan-out)
```

Subscriptions are stored in a plain text file matching the shape of `~/.co/contacts.txt` and `~/.co/whitelist.txt` — one `<address> <alias>` per line, `#` comments allowed.

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

`co sub` is the **sync verb**. With a target it syncs one publisher; with no target it syncs every entry in `~/.co/subscriptions.txt`. `list` and `remove` are named subcommands for the secondary operations.

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
  claude: installed 1 skill(s)
  codex: installed 18 skill(s)
  openclaw: installed 18 skill(s)
  cursor: installed 17 skill(s)

→ Restart your coding agent to load the new skills.
```

Re-running is idempotent — the file is deduped, the bundle is overwritten, the fanout is redone. This is also how you refresh: re-run the same command after the publisher pushes a new version.

Once a publisher is in `~/.co/subscriptions.txt`, you can use the alias as a shorthand for refresh: `co sub sync changxing` does the same thing.

**Options:**

| Option | Description |
|--------|-------------|
| `--relay <url>` | Override the relay (default `https://oo.openonion.ai`) |

### `co sub` — sync every subscription

With no subcommand, walks `~/.co/subscriptions.txt` and re-syncs each publisher in order.

```bash
co sub
```

If a publisher is unreachable the command stops at the failure — re-run after fixing the underlying issue. (Fail-fast is intentional: tolerating mid-loop failures hides real problems. Revisit if anyone hits this with many subscriptions.)

Cost-wise, each subscription costs `1 + N_skills` HTTP requests against the relay (1 profile + 1 per skill body). For 5 publishers with ~20 skills each that's ~100 requests — tolerable but not cheap. A future `profile-head` endpoint on the relay will let `co sub` skip publishers whose version hasn't changed; the CLI surface won't change when that lands.

### `co sub list` — local view only

Read `~/.co/subscriptions.txt` and the locally-mirrored `agent.json` to show version + skill count. No relay calls.

```bash
co sub list
```

**Output:**
```
                          Subscriptions
┏━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━┳━━━━━━━━┓
┃ Alias     ┃ Address                                                          ┃ Version ┃ Skills ┃
┡━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━╇━━━━━━━━┩
│ changxing │ 0xcd92510bb6cc090374ecc345ef8c19b9d3797624fd1fbf7e078a9372fc31… │ v0.1.0  │     18 │
└───────────┴──────────────────────────────────────────────────────────────────┴─────────┴────────┘

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

`~/.co/subscriptions.txt` is plain text. Edit it by hand if you like; `co sub` is just sugar.

```
# ~/.co/subscriptions.txt — agents you follow
# Format: <address> <alias>
# Managed by `co sub`. Re-run `co sub <address>` to refresh.
0xcd92510bb6cc090374ecc345ef8c19b9d3797624fd1fbf7e078a9372fc31bdc1 changxing
0xabc...                                                              alice
```

The mirrored bodies live separately at `~/.co/subs/<alias>/` — version and skill count are read from `<alias>/agent.json`, not from this list.

## Address vs alias

**First-time subscriptions require a 0x address.** Aliases are mutable: a publisher can change their alias, the relay can serve the wrong agent under a familiar name, and there's no way for the subscriber to tell after the fact. Subscribing by alias would be an MITM hole.

Once you've subscribed by address, the alias from the publisher's profile is recorded next to the address. From that point on you can use either:

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

## v1 limitations

Two known gaps, both upstream of the CLI:

1. **No signature verification.** The relay strips `signer` and `signature` from profile responses, so the client trusts the relay's word on what the publisher published. When the relay exposes the signature, `co sub` will verify locally before writing anything to disk. (Tracked.)
2. **No lazy version check.** Every `co sub` re-pulls the full profile + every body even if nothing changed. When the relay grows a `profile-head` endpoint, `co sub` will diff versions and only pull what's stale. The CLI surface won't change.

Both can land without changing the CLI surface — only the internals get smarter.

## Files touched

```
~/.co/subscriptions.txt              ← appended/rewritten on add/remove
~/.co/subs/<alias>/agent.json        ← mirrored publisher profile
~/.co/subs/<alias>/skills/<name>/SKILL.md  ← mirrored skill body
~/.claude/plugins/<alias>/           ← symlink (whole bundle)
~/.codex/skills/<alias>-<skill>/     ← per-skill symlinks
~/.openclaw/skills/<alias>-<skill>/  ← per-skill symlinks
~/.cursor/rules/<alias>-<skill>.mdc  ← file copy (frontmatter rewritten)
~/.kiro/steering/<alias>-<skill>.md  ← plain file copy
```

## See also

- [co announce](../announce.md) — the publisher side: sign `agent.json` and push to the relay
- [co setup](setup.md) — set up `~/.co/` identity and skill library
- [co skills](skills.md) — discover and import skills you've written yourself
- [Multi-Agent Networking](../network/README.md) — the broader relay/host/connect picture
