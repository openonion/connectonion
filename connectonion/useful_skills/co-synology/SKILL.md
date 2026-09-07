---
name: co-synology
description: Inspect a configured Synology NAS and manage its ordinary files and sharing links with the twenty-command co syno core.
---

# co syno

Use complete NAS paths and the user's selected profile. Read `--json` results,
including completeness and the one `next_command`; exit 1 may contain useful
partial evidence or a pending operation. Do not equate missing monitoring
coverage with health. Real-device acceptance of this candidate remains pending.

Use already authorized work as the scope. File writes and public sharing need
user intent; do not introduce a second approval when that intent is already clear.
Do not enable NAS transports, alter host-key trust, run service controls or
bypass TLS to make an inspection pass.

## Commands and parser parity

Every leaf accepts `--nas NAME`, `--json`, `--non-interactive` and `--timeout
SECONDS`. Common flags work before groups or after leaves; conflicting repeated
values are usage errors. Use actual `--help` for any leaf before guessing flags.
The provider waiting budget defaults to 60 seconds, maximum 3600.

| Command | Arguments/options |
| --- | --- |
| `co syno login` | `--name NAME`, `--url HTTPS_URL` or `--quickconnect ID`, `--username USER`, `--password-stdin`, `--ca-cert FILE`, `--credential-store keyring\|file`, `--monitoring FILE`, `--snmp-secrets-file FILE` |
| `co syno logout` | Clear local auth; keep profile settings |
| `co syno nas list` | Saved profiles/default |
| `co syno nas use NAME` | Select default |
| `co syno status` | `--refresh`, or `--operation ID [--wait]` |
| `co syno network status` | `--refresh` |
| `co syno storage status` | `--refresh` |
| `co syno storage disks` | `--refresh` |
| `co syno service list` | `--running`, `--refresh` |
| `co syno ls [PATH]` | `--limit N`, `--cursor TOKEN`, `--sort name\|modified\|size`, `--order asc\|desc` |
| `co syno info PATH` | Full NAS path |
| `co syno search QUERY --in PATH` | `--glob`, `--type file\|directory\|all`, `--limit N`, `--cursor TOKEN` |
| `co syno download PATH` | `--to LOCAL`, `--recursive`, `--overwrite` or `--skip-existing`, `--dry-run`, migration `--listing ID` |
| `co syno upload LOCAL REMOTE_DIR` | `--recursive`, `--overwrite` or `--skip-existing`, `--dry-run` |
| `co syno mkdir PATH` | `--parents`, `--dry-run` |
| `co syno copy SOURCE DEST` | `--recursive`, `--overwrite`, `--dry-run` |
| `co syno move SOURCE DEST` | `--overwrite`, `--dry-run` |
| `co syno share create PATH` | `--expires YYYY-MM-DD` or `--no-expiry`, `--password` or `--password-stdin`, `--yes`, `--dry-run`, migration `--listing ID` |
| `co syno share list` | `--limit N`, `--cursor TOKEN`, `--show-url` |
| `co syno share revoke ID` | `--yes`, `--dry-run` |

`--last` and `-n` alias `--limit` (default 20, range 1–1000). Legacy `get`, `put`,
`shares` and `share PATH` alias download/upload/share list/share create, with the
same options and safeguards. Numeric references always require their explicit
frozen `--listing ID`; the old mutable last-list cache is ignored. No implicit
interactive row resolution is used. Canonical full paths are preferable.

## Read-only workflow

```bash
co syno nas list --json
co syno --nas home status --json
co syno --nas home ls /home/docs --json
co syno --nas home search invoice --in /home/docs --type file --json
co syno --nas home share list --json
```

Bare `co syno` lists accessible shared folders. `/` is the share inventory, not
the DSM system root. `ls` now defaults to name ascending; file size 0 means an
empty file, while directory size is null. Search is names-only and requires
explicit scope; patterns need `--glob`. Search waits for a finished snapshot
and requests cleanup before publishing rows. Incomplete searches fail.

Follow the exact pagination command with unchanged parameters. Cursors and
listing contexts expire after 15 minutes and bind the selected profile/account.
A second process's listing never changes an earlier row token. Live directory
and link pages are not snapshots and may change between requests.

## Connection sources

Verified HTTPS proves File Station access and supplies hostname/client timing.
SNMPv3 authPriv supplies system/disk/RAID/interface indicators. SSH supplies the
actual enumerated service state. HTTPS login does not authorize configuring or
enabling the optional transports. Missing sources remain unavailable; device
health OIDs and service commands vary by DSM/model.

Profiles use the global configuration directory. Secrets use the OS keyring,
or an explicitly selected POSIX private-file fallback. Legacy `keys.env`
connections require verified login; do not copy credentials into argv. OTP is
interactive-only and never saved. JSON never prompts. `--password-stdin` reads
only a password, never an OTP or multi-field secret record.

`login --monitoring FILE` uses non-secret `snmp`/`ssh` configuration. The CLI
reference documents its schema. SNMP keys are prompted or read from the explicit
private `--snmp-secrets-file`; SSH requires a named key and known-host file.
Do not enable services or enroll unknown host keys as a workaround.

## Transfers and sharing

```bash
co syno download /home/docs/report.pdf --to ./Downloads/ --dry-run --json
co syno upload ./report.pdf /home/docs --dry-run --json
co syno mkdir /home/docs/archive --parents --dry-run --json
co syno move /home/docs/report.pdf /home/docs/archive/final.pdf --dry-run --json
co syno share create /home/docs/archive/final.pdf --expires 2026-09-30 --yes --json
co syno share list --json
co syno share revoke LINK_ID --yes --json
```

Use an existing local destination directory or an exact filename with an
existing parent. Missing trailing-slash directories fail. Upload requires an
existing remote directory. Directory transfers require `--recursive`, preserve
base names and empty directories, and need an explicit merge choice if the
base target exists. Type conflicts always fail. There is no overwrite by default.
`--yes` never implies overwrite. Copy/move never merge an existing directory tree.

Dry-run may load an existing saved session from the credential store, but never
refreshes auth, prompts, persists caches/state or submits mutations. It is a
preflight, not a reservation. It does not read a share password; password
validation is deferred. Read every completed/skipped/failed/unstarted item after
a partial transfer. Do not assume recursive work or uploads are atomic.

A known pending copy/move has an `operation_id`. Inspect that same task:

```bash
co syno status --operation OPERATION_ID --wait --json
```

Status never submits another write. Exact renamed destinations can have recorded
staging steps; `continuation_required` supplies the original command to resume.
A submission without a returned task ID is `submission_unknown`; inspect remote
paths rather than blindly retrying. NAS restart/task eviction is not proof of
failure. Receipts block automatic replay of uncertain steps.

Sharing requires an explicit NAS-local date or no-expiry. Unattended create and
revoke require `--yes`; a protected link password is at most 16 characters and
is never truncated. Create returns its URL. Inventory hides URLs unless
`--show-url` is requested. Revoke removes only the link, never the source file.

## Output and exits

All leaves emit a schema-1 JSON envelope with `provider`, `nas`, `command`, `ok`,
`status`, `complete`, `data`, `error`, and `next_command`. Human results go to
stdout and tips to stderr. Use JSON for scripting.

| Exit | Meaning |
| --- | --- |
| 0 | Complete or empty successful result |
| 1 | Operational/partial failure, pending/unknown operation, or declined confirmation |
| 2 | Usage error or an interaction-only option without a terminal |
| 130 | Interrupted; inspect state before repeating writes |

Before reporting completion, verify the requested outcome, relevant post-write
inventory, and all partial/unknown fields. Keep unavailable monitoring, local
hash evidence, live device coverage and release readiness distinct. The core
has no public delete, service control, package management or shared-root creation.
