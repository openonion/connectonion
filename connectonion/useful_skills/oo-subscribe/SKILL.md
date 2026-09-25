---
name: oo-subscribe
description: Follow, refresh, inspect, or remove another publisher's ConnectOnion skills with co sub. Use for published agent subscriptions; use co skills for importing local skills.
---

# Follow published ConnectOnion skills

Use the installed `co sub` commands. Read `co sub --help` and the selected
subcommand's `--help` when syntax or behavior differs from this skill. The CLI
fetches the profile and skill bodies, verifies the publisher's signature and
revision, mirrors the public bodies, and installs them into detected coding
agents. No subscriber key, `co init`, or publisher approval is required to
follow public skills.

| Goal | Command |
|---|---|
| Follow a publisher for the first time | `co sub sync <full-0x-address>` |
| Refresh one publisher already in the local list | `co sub sync <address-or-local-alias>` |
| Refresh all local subscriptions | `co sub` |
| See locally recorded subscriptions | `co sub list` |
| Stop following one | `co sub remove <address-or-local-alias>` |

## Choose and verify the publisher

First-time follow requires the publisher's complete address (`0x` plus 64 hex
characters), obtained from the publisher or another trusted channel. A bare
alias only works after that address has been pinned locally. If the user gives
only an alias, run `co sub list` to see whether it is already pinned. Otherwise
ask for the full address; do not guess it or resolve an untrusted alias through
the relay.

Run `co sub sync <full-0x-address>` once. Read the entire result. A successful
subscription records the address and signed alias in
`~/.co/subscriptions.txt`; published bodies are mirrored under
`~/.co/subs/<alias>/skills/`. The CLI verifies the `profile-v2` signature and
monotonic revision before installing, rejects unsigned or older content, and
removes a remote skill's `tools:` grant. A signature identifies the publisher;
it does not establish that the skill's instructions are safe or useful. Review
the mirrored `SKILL.md` before using it for consequential work.

Check `co sub list` for the pinned address, alias, and profile version. Its
Skills column counts profile entries, including entries whose bodies were not
published; use the sync output's mirrored and installed counts to describe what
became available. If an agent reports a positive installed count, tell the user
to restart that coding agent. If nothing was installed, say so and do not ask
for a restart. A publisher can list a skill's metadata while withholding its
body; a later sync may pick it up if the publisher makes it public.

## Refresh or remove

`co sub` pulls every saved publisher in order and stops at the first failure.
For one publisher, use `co sub sync <address-or-local-alias>`; an alias here is a
shortcut to the already-pinned address. Read the counts again rather than
assuming that a newer profile changed installed skills.

For an explicit unsubscribe request, identify the exact entry with `co sub
list`, then run `co sub remove <address-or-local-alias>`. This removes the local
record, mirror, and installed fan-out. The authenticated revision watermark in
`~/.co/subscription-state/` remains, so a later resubscribe cannot erase
rollback protection. `Not subscribed` is a no-op result, even if the command
exits successfully.

## Recovery and boundaries

- Unknown first-time alias: get the complete publisher address, then run
  `co sub sync <full-0x-address>`.
- Unsigned or `profile-v1` profile: ask the publisher to update ConnectOnion
  and run `co announce` again.
- Rollback or equivocation: keep the local watermark. Verify the discrepancy
  with the publisher; they must announce intended content at a higher revision.
- Network or missing-body failure: report the actual error and retry the CLI
  after it is resolved. Do not write a replacement `SKILL.md` from an error
  response or bypass signature checks.

This is a local pull relationship. It sends no SUBSCRIBE request, has no
publisher accept queue, and receives no automatic update push. Do not re-create
the relay protocol with `curl` or handwritten signing code; `co sub` owns the
verification and file layout. Use `co skills discover` and `co skills copy` for
skills already on this machine rather than a publisher's relay bundle.
