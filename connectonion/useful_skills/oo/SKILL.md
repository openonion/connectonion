---
name: oo
description: Connect to a remote ConnectOnion agent, set up a publishable identity, publish selected skills, or follow and sync another publisher. Use for a 0x agent address, /oo, co announce, or co sub workflows; not for ordinary local-agent tasks.
---

# Connect, publish, and follow with `oo`

Route the request before running anything:

| User wants | Action |
|---|---|
| Ask or delegate to a remote `0x...` agent | Use the Connect flow |
| Create the global identity and skill library | Use Setup |
| Share selected local skills | Use Publish |
| Follow a publisher for the first time | Run `co sub sync <0xaddress>` |
| Refresh one already-pinned publisher | Run `co sub sync <address-or-local-alias>` |
| Refresh everyone | Run `co sub` |
| See or remove subscriptions | Run `co sub list` or `co sub remove <address-or-local-alias>` |
| Accept or reject a follower | Explain that public subscriptions have no publisher-approval step |

## Keep the protocol layers straight

- OIP is the live, authenticated Agent protocol: CONNECT, INPUT, EXEC, events,
  OUTPUT, session ownership, modes, approvals, and cancellation.
- ANNOUNCE publishes a signed public profile to the relay. `co announce` adds a
  portable `profile-v2` signature and monotonic revision.
- `co sub` is a local pull/sync relationship. It is not a SUBSCRIBE message,
  push channel, access-control handshake, or proof that the content is safe.

Do not recreate HTTP endpoints, signing, profile verification, rollback state,
or fan-out in ad-hoc Python. The `co` CLI owns those details.

## Connect

Require one exact 66-character address (`0x` plus 64 hex characters) and a task.
Use the installed SDK; it already probes safe direct endpoints and falls back to
the relay:

```python
from connectonion import connect

remote = connect("0x...")
response = remote.input("the user's task", timeout=300)
print(response.text)
print("done=", response.done)
```

`connect()` uses the current project's identity, then `~/.co`. If neither
identity exists, tell the user to run `co init` for a project identity or Setup
below for a global publishable identity. Never generate an identity silently.

When `response.done` is false, return the remote question to the user. Keep the
same `remote` object for the answer when the execution environment supports a
persistent Python process. Otherwise include the prior question and answer in a
new request; do not pretend the old session was resumed.

## Setup

Ask for or infer a lowercase alias and a useful one-line bio, then show the exact
command before running it:

```bash
co setup --name <alias> --bio "<one-line bio>"
```

`co setup` creates or refreshes the global `~/.co/` identity, profile, and skill
library. If `~/.co/agent.json` already exists, do not use `--force` until the
user sees the conflicting alias/bio; the command backs up the file, but it still
replaces the active profile.

## Publish

Publishing is public. Before changing any `publish` flag, inspect
`~/.co/agent.json` and the corresponding `~/.co/skills/<name>/SKILL.md` files.

Only publish a skill now when all of these are true:

- its `SKILL.md` is useful and self-contained without `scripts/`, `references/`,
  `assets/`, local private files, or undisclosed MCP/app dependencies;
- it contains no secrets, customer data, private contacts, machine-specific
  paths, or personal instructions that should stay local;
- it preserves user authorization at the action boundary and does not treat the
  publisher's permission preferences as the subscriber's permission;
- its name and description are meaningful when shown publicly.

Current distribution carries only `SKILL.md`. A skill that needs sibling files
is not portable yet; leave it unpublished rather than shipping a broken copy.

Important visibility rule: every skill's name and description are listed in the
public profile. `publish: true` controls whether its full `SKILL.md` body is also
public. `publish: false` does not make the metadata private.

After the user approves the exact bodies, change only their existing
`agent.json.skills[].publish` values. Then validate and publish:

```bash
co announce --dry-run
co announce
```

Read the dry-run payload and confirm the alias, bio, listed skill count, public
body count, names, and absence of private content. `co announce` creates the
signed revision; a human-readable `version` is display metadata, not the
rollback mechanism.

Give the publisher's full `0x` address to subscribers through a trusted channel.
Do not tell first-time subscribers to resolve an alias.

## Follow and sync

First-time follow requires the publisher's full address:

```bash
co sub sync <0xaddress>
```

The command fetches the public profile and bodies, verifies the publisher's
`profile-v2` signature against that pinned address, rejects rollback or
equivocation, mirrors the bundle under `~/.co/subs/`, removes a subscribed
skill's `tools:` grant, and fans it out to detected coding agents.

After the first valid sync, the signed alias is stored locally and may be used as
a refresh shortcut:

```bash
co sub sync <local-alias>
co sub
co sub list
co sub remove <address-or-local-alias>
```

The relationship is pull-based. There is no publisher accept/reject queue and no
automatic BUNDLE_UPDATE push. Re-run `co sub` to get updates. Removing a
subscription deliberately retains `~/.co/subscription-state/<address>.json` so
unsubscribe/resubscribe cannot erase rollback memory.

If the command installs anything into a coding agent, tell the user to restart
that agent. If it says only that bodies were mirrored or no skills were
installed, do not claim a restart is required.

## Trust and recovery

- A valid signature proves who published the bytes, not that the instructions
  are safe, high quality, compatible, or appropriate for the user's machine.
- If a first-time target is an alias, obtain the full address out of band and run
  `co sub sync <0xaddress>`.
- If a profile is unsigned or `profile-v1`, the publisher must update
  ConnectOnion and run `co announce` again.
- On rollback or equivocation, do not delete the local watermark. Verify with the
  publisher; intentional old content must be re-announced at a higher revision.
- `co sub list` with no entries and `co sub remove` for an unknown target are
  successful no-op outcomes, so read their output rather than inferring state
  only from exit code.
