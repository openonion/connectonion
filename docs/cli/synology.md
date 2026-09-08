# Synology CLI (co syno)

ConnectOnion 1.8.4 provides twenty everyday NAS commands: connection profiles,
read-only inspections, ordinary files and sharing links. Regression tests and
focused journeys on one physical NAS cover file operations and sharing. Password,
already-expired link and revocation behavior were also checked in a browser.
This does not imply a hardware matrix or midnight-transition coverage. See the
[release notes](../releases/1.8.4.md) for the evidence and remaining limits.

```bash
co syno login --name home --url https://nas.example:5001 --username alice
co syno status --json
co syno ls /home/docs --json
co syno search invoice --in /home/docs --type file --json
co syno download /home/docs/invoice.pdf --to ./Downloads/
```

The destination directory in this example must already exist. Paths are NAS
shared-folder paths such as `/home/docs`, never an implicit remote working
directory. `/` lists accessible shares, not DSM's system root.

## QuickConnect connection

`co syno login` accepts a QuickConnect ID or an HTTPS URL at its first prompt.
For an explicit invocation, use `co syno login --quickconnect YOUR_ID --username YOUR_USER`.
If direct addresses cannot answer, discovery requests Synology's temporary HTTPS
relay and verifies the regional DSM endpoint within the command timeout. The
public QuickConnect webpage alone is not a DSM API endpoint. Certificates are
always verified; discovery never sends your NAS password.

## Connection and monitoring

Install the optional adapters with `pip install 'connectonion[synology]'`.
HTTPS File Station works with the main package. Login verifies authenticated
File Station access before publishing a profile. A failed replacement leaves
the last saved profile selected. The first profile becomes default; adding
another does not switch it.

TLS verification is always enabled. For a private CA, supply `--ca-cert FILE`.
`--quickconnect ID` discovers and probes HTTPS candidates within a bounded
budget; a certificate mismatch does not enable an insecure fallback. A verified
LAN endpoint may stop working after changing networks; explicitly log in using
a reachable verified URL.

Passwords are prompted only in a real terminal. `--password-stdin` reads one
password line; it never doubles as OTP input. Required OTP is prompted only in
an interactive login and is never saved. JSON and non-interactive commands
cannot perform initial OTP login.

Profiles live under the selected global configuration directory's `synology/`
subdirectory (normally `~/.co/synology`). They contain settings and opaque
credential references. Secrets use the OS keyring by default. The explicit
`--credential-store file` fallback uses private files on POSIX and is unsupported
on Windows. Logout retains settings, clears local authentication and reports
whether remote session invalidation was confirmed.

`SYNOLOGY_*` values in an old `keys.env` are not silently imported. Re-run
verified login to migrate. No session or password is written back to that file.
The existing file is not deleted or rewritten by migration.

Optional monitoring is configured during login, without enabling services on
the NAS. `--monitoring FILE` accepts a JSON file containing only non-secret
`snmp` and/or `ssh` settings:

```json
{
  "snmp": {
    "host": "nas.example", "port": 161, "username": "nas-reader",
    "auth_protocol": "SHA256", "priv_protocol": "AES128", "context": ""
  },
  "ssh": {
    "host": "nas.example", "port": 22, "username": "nas-reader",
    "key_file": "~/.ssh/nas-reader", "known_hosts": "~/.ssh/known_hosts"
  }
}
```

SNMP authentication and privacy keys are prompted, or read from an explicitly
selected private JSON file using `--snmp-secrets-file FILE`. That file contains
only the nonempty fields `snmp_auth` and `snmp_priv`. It is separate from the
non-secret monitoring configuration. Secrets never go on argv. Replacing a
profile supplies its monitoring configuration again; it does not borrow the
previous NAS/account's adapter credentials.

SSH uses the named key and known-host file, rejects unknown host keys, and runs
only the two documented `synoservice --list` commands. It does not enroll host
keys, enable SSH/SNMP, use a password fallback or invoke service controls.

| Inspection | Field source and limits |
| --- | --- |
| `status` | Verified File Station identity/access plus each configured monitor. Missing sources remain unavailable; partial coverage exits 1. |
| `network status` | HTTPS endpoint/TLS/timing describes the client. SNMPv3 IF-MIB describes NAS interfaces; IP-MIB adds available IPv4 addresses. IPv6 is explicitly unavailable in this adapter. |
| `storage status` | SNMPv3 RAID rows, status and capacity counters. Units remain provider units; usage percentage uses matching counters. Rows are not summed or labeled as inferred volume/pool topology. |
| `storage disks` | SNMPv3 disk identity, deployment, temperature and available health indicators. Deployment normal does not imply missing health is normal. Full health OID coverage requires DSM 7.1 or later. |
| `service list` | Actual SSH service enumeration, with a separate running set. An unavailable command/grant is an error, not a list of API names. |

Results include `checked_at`. All current inspections are fresh, so `--refresh`
performs the same live work. No NAS model or DSM version has passed this task's
live acceptance yet. File Station APIs negotiate required versions; the
implementation targets documented DSM 6.0+ File Station behavior, with DSM 7.1+
needed for the additional disk-health OID. See the
[source/onboarding decision](../design-decisions/070-synology-inspections-and-durable-operations.md).

## Command inventory

Every leaf has parser-generated `--help`, an example, and the common options
`--nas NAME`, `--json`, `--non-interactive`, and `--timeout SECONDS`. Common
options work before a group or after a leaf. Repeated conflicting values are
usage errors. The default network waiting budget is 60 seconds, with a maximum
of 3600. Interactive typing time is separate from provider waiting.

| Command after `co syno` | Arguments and options |
| --- | --- |
| `login` | `--name`, `--url` or `--quickconnect`, `--username`, `--password-stdin`, `--ca-cert`, `--credential-store`, `--monitoring`, `--snmp-secrets-file` |
| `logout` | Retain connection settings; clear authentication |
| `nas list` | List saved profiles and the default |
| `nas use NAME` | Select the saved default |
| `status` | `--refresh`, or `--operation ID` with optional `--wait` |
| `network status` | `--refresh` |
| `storage status` | `--refresh` |
| `storage disks` | `--refresh` |
| `service list` | `--running`, `--refresh` |
| `ls [PATH]` | `--limit`, `--cursor`, `--sort name\|modified\|size`, `--order asc\|desc` |
| `info PATH` | Complete NAS path |
| `search QUERY --in PATH` | `--glob`, `--type file\|directory\|all`, `--limit`, `--cursor` |
| `download PATH` | `--to`, `--recursive`, `--overwrite` or `--skip-existing`, `--dry-run`, migration `--listing` |
| `upload LOCAL REMOTE_DIR` | `--recursive`, `--overwrite` or `--skip-existing`, `--dry-run` |
| `mkdir PATH` | `--parents`, `--dry-run` |
| `copy SOURCE DEST` | `--recursive`, `--overwrite`, `--dry-run` |
| `move SOURCE DEST` | `--overwrite`, `--dry-run` |
| `share create PATH` | `--expires YYYY-MM-DD` or `--no-expiry`, `--password` or `--password-stdin`, `--yes`, `--dry-run`, migration `--listing` |
| `share list` | `--limit`, `--cursor`, `--show-url` |
| `share revoke ID` | `--yes`, `--dry-run` |

`--last` and `-n` alias `--limit`, whose default is 20 and range is 1–1000.
`get`, `put`, `shares`, and `share PATH` remain migration aliases with the
canonical options. New help examples and recovery commands use canonical names.

## Listings and search

`ls` requests DSM name-ascending order, replacing the historical modified-time
order. DSM can group directories before files; pagination preserves that order.
Directories have `size: null`; an empty file has `size: 0`. Machine output keeps
complete paths. Live directory/link pages can change between requests; they
are not immutable snapshots.

Cursors bind the profile identity and original path/query/type/sort/order/limit.
Repeat the same parameters with `--cursor TOKEN`, or use the emitted next command.
A cursor from another profile, changed query, corrupt record, or an expired
15-minute context is rejected. Replacing a profile invalidates its old contexts.

Search requires `--in` and searches names recursively, not file contents.
Patterns require explicit `--glob`; ordinary queries become substring matches.
The client waits for completion, retrieves up to 10,000 results, and requests
server-task cleanup before publishing a local snapshot. Cleanup is also
attempted on timeout, failure and interruption. A disconnected NAS can prevent
confirmation; this is not reported as successful empty output.

Legacy numeric rows always require the exact `--listing ID` printed in the
corresponding listing. The old mutable last-list cache is ignored. This also
applies in interactive mode, which is deliberately stricter than an implicit
last-row confirmation. Prefer complete paths:

```bash
co syno get 3 --listing LISTING_ID --to ./Downloads/
co syno download /home/docs/report.pdf --to ./Downloads/
```

## Transfers and ordinary directories

No overwrite is the default. Choose `--overwrite` or `--skip-existing` explicitly;
they cannot be combined. Type conflicts always fail. Existing directory targets
require an explicit merge choice. Recursive uploads/downloads preserve the
source base directory and empty directories; a directory is never reconstructed
from a DSM ZIP response.

An existing local directory receives the source name. A non-directory local
path is an exact filename, whose parent must exist. A missing trailing-slash
directory is an error. Upload requires an existing NAS destination directory.
`mkdir --parents` creates ordinary directories inside an existing share, never
new DSM shared roots.

Preflight rejects local symlinks and remote resolved-path or virtual-mount
escapes. POSIX downloads pin parent directories with no-follow descriptors.
Windows validates the existing path chain but does not provide the same POSIX
ancestor-descriptor race protection. File Station has no compare-and-swap
transfer primitive; a concurrent remote filesystem edit remains a race.

Downloads write a private temporary file, validate available byte-length
evidence and atomically place the result. Output SHA-256 describes downloaded
bytes, not an invented server hash. Failures preserve an existing local file.
Uploads report DSM acknowledgement and local size evidence. Their ambiguous
responses are never automatically retried; inspect remote state first.

Recursive output records completed, skipped, failed and unstarted items.
Partial transfers are not atomic. `--dry-run` performs bounded preflight using
an existing saved session and can read the credential store to load that
session. It does not refresh authentication, prompt, save state, create caches,
write files or submit mutations. A dry-run is not a reservation or permission
guarantee. Password-protected share previews defer secret validation.

## Copy, move and pending operations

An existing destination directory receives the source name; otherwise the
specified path is the exact destination. There is no existing-directory-tree
merge. Copying a directory requires `--recursive`; moves include directory
contents. Self-descendant operations and type conflicts are rejected.

Same-name destinations use DSM's CopyMove task. Exact new names may require an
owned staging directory and rename/placement steps. This can temporarily move a
source into the reported staging path; it is not an atomic rename across
folders. Only the operation's empty staging directory is cleaned up.

Each mutation step is recorded before submission. Known task IDs survive CLI
restarts; unknown submissions are not replayed. A timeout with a task ID reports
`operation_pending` and an `operation_id`:

```bash
co syno status --operation OPERATION_ID --wait --json
```

Status only observes the current task. If a staged workflow needs another write
step, it reports `continuation_required` and the exact original copy/move command
to resume. Repeating that command resumes the recorded workflow rather than
resubmitting the earlier task. If no task ID was received, `submission_unknown`
requires remote inspection. Task history may disappear after a NAS restart;
that does not prove the operation failed. Receipts are not automatically expired.

`--wait` requires `--operation`; `--operation` and `--refresh` cannot be combined.

## Sharing

```bash
co syno share create /home/docs/report.pdf --expires 2026-09-30 --yes
co syno share list --json
co syno share list --show-url --json
co syno share revoke LINK_ID --yes
```

Interactive create asks for a date or explicit no-expiry, then confirmation.
Unattended create requires an expiry choice and `--yes`. Dates are NAS-local
calendar dates; the result does not invent an unknown NAS timezone. Passwords
are prompted with `--password` or read from one line with `--password-stdin`.
The negotiated v3 contract accepts at most 16 characters; no truncation or
silent weakening occurs.

Creation reads the new link back from DSM and checks its identity, password
protection flag and expiry date before returning its URL with
`settings_verified: true`. The expiry includes DSM's returned time, when present.
If settings differ, the CLI attempts to revoke only that newly identified link
and reports a failure. Uncertain readback or revocation requires inspecting
`co syno share list` before retrying; it never silently creates another link.
This settings check does not replace testing access through the sharing page.

Inventory hides bearer URLs unless `--show-url`
is given, and includes ID/path/expiry/protection/provider status. Revocation
requires confirmation or `--yes` and never deletes the source. There is no
public file-delete or service-control command in this core.

## Output and exits

Every leaf supports one schema-1 JSON envelope with `provider`, `nas`, `command`,
`ok`, `status`, `complete`, `data`, `error`, and a quoted `next_command`.
`--json` never prompts or prints ANSI. Human results are readable JSON on stdout;
the one recovery hint goes to stderr. Human output is not a scripting API.

| Exit | Meaning |
| --- | --- |
| 0 | Completed operation or an empty successful list |
| 1 | Operational failure, partial coverage/transfer, pending/unknown work, or declined confirmation |
| 2 | Usage/input error or an interaction-only option in unattended mode |
| 130 | Interrupted; inspect remote state before repeating a write |

Read the result as well as the exit code. Missing authentication, unsupported
sources, stale cursors, conflicts, incomplete searches and uncertain writes
have distinct error codes. Empty results never suggest downloading a nonexistent
first row.

For opt-in command acceptance, run `scripts/acceptance/synology_release.py` with
the candidate's Python and explicit `--nas`, `--parent`, and
`--allow-fixture-writes`. Add `--allow-test-share` only when synthetic sharing
links are wanted. The script creates a unique fixture directory, checks command
results and transfer bytes, then removes its own files and links. It retains the
owner login. Reports may contain local test paths and should be reviewed before
sharing. No real-device reports are included in this change.
