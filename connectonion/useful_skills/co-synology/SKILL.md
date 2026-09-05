---
name: co-synology
description: Safely inspect and manage the user's Synology File Station files with `co syno`. Use when the user asks about their NAS files, folders, downloads, uploads, or public sharing links.
---

# co syno

Use the user's configured Synology NAS from the shell. Start with read-only
commands. Uploading, downloading, and creating a public link change state; do
those only when the user asked for them.

## Choose the command

| Need | Command |
|---|---|
| Verify access and see the TLS posture | `co syno status` |
| List shared folders or one folder | `co syno ls [nas-folder]` |
| Find a file by name | `co syno search <query> [--in <nas-folder>]` |
| Audit existing public links | `co syno shares` |
| Download a listed file | `co syno get <#> [--to <local-path>]` |
| Upload a local file | `co syno put <local-path> <nas-folder>` |
| Create a public link | `co syno share <#>` |
| Configure or reconnect | `co syno login [--url <https-url>]` |

Use `--json` with `status`, `ls`, `search`, and `shares` when parsing output.
Those commands emit one stable envelope with `schema_version`, `ok`, `command`,
`data` or `error`, and `next_command`.

## Read-only first

```bash
co syno status --json
co syno ls --json
co syno ls /home -n 50 --json
co syno search invoice --in /home --json
co syno shares --json
```

Numbers belong to the most recent `ls` or `search` result. A later listing
replaces the cache, so never carry `#3` across listings. Piped table output is
tab-separated and keeps the full NAS path plus its final next-command tip.

## Transfers and public sharing

```bash
co syno get 3 --to ./downloads
co syno put ./report.pdf /home/docs
co syno put ./report.pdf /home/docs --overwrite
co syno share 3
```

`put` writes to the NAS. `--overwrite` may replace an existing remote file.
`get` writes locally and can replace a same-named local file. `share` creates a
public link with no expiry or password; check `co syno shares` before and after.
There is deliberately no delete command because File Station deletion is
permanent through this API.

## Known connection limits

- Saved credentials and the session id live in `~/.co/keys.env`.
- NAS TLS certificate verification is currently disabled. `co syno status`
  reports that explicitly. Do not describe HTTPS alone as server identity proof.
- DSM accounts that require a one-time 2FA code are not supported by this CLI yet.
  Use a suitable least-privilege NAS account or stop and ask the user.

## Exit codes

| Exit | Meaning | Next command |
|---|---|---|
| `0` | Success, including an empty read-only listing | Use the literal `next_command` in JSON or the last printed command |
| `1` | Not configured, NAS/API failure, stale listing number, or unsafe local input | `co syno status --json` |
| `2` | Invalid command or argument | `co syno --help` |

For exit `1`, read the printed recovery command: a missing configuration points
to `co syno login`, while a stale listing points to `co syno ls`.

## Done checklist

- [ ] Began with `co syno status --json`
- [ ] Used `ls`, `search`, and `shares` before any write
- [ ] Used a listing number only from the immediately preceding output
- [ ] Obtained user intent before upload, overwrite, download, or public sharing
- [ ] Reported the TLS-verification and 2FA limitations when relevant
- [ ] Read and followed the one literal next command in the result
