# co-synology

Safely inspect and manage a user's Synology File Station files with `co syno`.

## Install

```bash
co copy co-synology
# → .co/skills/co-synology/SKILL.md
```

## Usage

```text
/co-synology find the latest invoice on my NAS, but do not download it
```

## What the skill teaches

The skill routes NAS requests to the smallest command, starts with read-only
`status`, `ls`, `search`, and `shares` calls, explains the short-lived listing
numbers, and marks upload, overwrite, download, and public-link creation as
state-changing operations. It also records the current TLS-verification and 2FA
limitations so an agent does not claim a stronger connection than the CLI has.

See [Synology CLI](../cli/synology.md) for the canonical command reference.
