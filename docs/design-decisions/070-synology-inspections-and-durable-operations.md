# 070: Synology inspection sources and durable file operations

Status: implemented candidate; real NAS acceptance pending. Target: 1.8.4.
Issues: #1429 and #1445. Existing PR: #1435.

The old tool called a successful File Station request “status,” disabled TLS
verification and shared one mutable env/session/listing cache. That could prove
reachability while saying nothing about disks or interfaces. The new core uses
separate, explicit sources and preserves uncertainty after file writes.

## Sources and onboarding

Verified HTTPS File Station Info/List supplies hostname, authentication,
connectivity and client request timing. It does not imply NAS interface health.
Explicit SNMPv3 authPriv supplies IF-MIB interfaces, IP-MIB IPv4 associations,
Synology system, RAID and disk indicators. Explicit SSH key plus known-host
verification supplies service names and a separately enumerated running set.

SNMP supports SHA/SHA256 with AES128, no community or no-auth fallback. SSH runs
only `/usr/syno/sbin/synoservice --list` and the same command with `running`.
Unknown host keys are rejected; no transport is enabled during setup. API.Info
names are not substituted for running services. A NAS lacking the documented
service enumerator reports unsupported source; no unverified command fallback
has been added.

One field has one source. Disk deployment and health remain separate. RAID rows
are provider rows, not inferred volume/pool topology; their capacities are not
summed. The guide does not establish counter units sufficiently for this
implementation to label them bytes, so counters retain provider units and
same-unit pairs support a usage percentage. Network IPv6 remains explicitly
unavailable. Missing indicators are not normal/healthy defaults.

Onboarding stays in `login --monitoring FILE`, with non-secret SNMP/SSH settings
in that file. SNMP authentication keys come from terminal prompts or a named
private secret file. SSH key/known-host paths are explicit. HTTPS login verifies
File Station access before atomic profile publication. Monitoring can still be
unavailable afterward and is reported independently. Failed credential or
profile replacement preserves the previous selected record.

Profiles have unique identities and opaque credential references. Actual OS
keyrings are preferred; a protected-file fallback must be explicitly selected
and is POSIX-only. New profile creation does not switch an existing default.
Session refresh is serialized and checks that the profile/account record has
not changed. Logout attempts remote invalidation and clears local auth even if
that attempt fails. OTP is transient and interactive-only.

## DSM baseline and evidence

The adapter targets capability-negotiated File Station versions documented for
DSM 6.0+: Info/List/Search/Download/Upload/CreateFolder/Rename/Delete v2,
CopyMove/Sharing v3, Auth v3 for OTP. Full disk-health fields require the DSM 7.1+
OID; earlier deployment status alone is insufficient. The service path is
supported only where the documented enumerator exists and the selected account
can execute it. This is a capability baseline, not a claim of tested model support.

| NAS/model/DSM | Evidence |
| --- | --- |
| Real NAS | Not supplied for this task; live matrix remains empty |
| Synthetic DSM HTTP fixtures | Negotiation, OTP, stale SID, errors, paging, transfers and operation receipts |
| Synthetic monitoring fixtures | Field/source separation and unavailable indicators |
| Installed optional libraries | PySNMP 7.1 and Paramiko 4 in an isolated dependency target; real transport acceptance pending |

Primary references checked 7 September 2026:
[File Station API](https://global.download.synology.com/download/Document/Software/DeveloperGuide/Package/FileStation/All/enu/Synology_File_Station_API_Guide.pdf),
[Synology MIB guide](https://global.download.synology.com/download/Document/Software/DeveloperGuide/Firmware/DSM/All/enu/Synology_DiskStation_MIB_Guide.pdf),
[Synology administration CLI](https://global.download.synology.com/download/Document/Software/DeveloperGuide/Firmware/DSM/All/enu/Synology_DiskStation_Administration_CLI_Guide.pdf),
[PySNMP asyncio API](https://docs.lextudio.com/pysnmp/v7.1/docs/api-reference),
[Paramiko client API](https://docs.paramiko.org/en/4.0/api/client.html).

## State, file races and durable operations

Directory/link cursors bind profile identity and query parameters but do not
claim live directories are snapshots. Searches finish, fetch a bounded snapshot
and request server cleanup before client paging. Frozen listing tokens replace
the mutable last-list file. Numeric references require a token even interactively;
this is a deliberate tightening beyond the issue's optional confirmation path.

Downloads use private temporary files, length checks and atomic placement.
POSIX pins the ancestor chain with no-follow directory descriptors. Windows
validates existing ancestors but lacks that descriptor guarantee. Remote
real-path preflight rejects resolved-path and virtual-mount escapes, and files
are checked again immediately before download. File Station lacks a comparable
CAS primitive: concurrent remote filesystem edits cannot be promised race-free.

An asynchronous timeout with a task ID differs from a lost submission response.
Each file-operation step is saved before sending it. The former can be inspected
by ID; the latter is not replayed. Task history is not assumed to survive a NAS
restart. Receipts are not forgotten automatically.

CopyMove accepts a destination directory, not an arbitrary new filename. A
same-parent move can rename directly. Other exact-name destinations use a unique
owned staging directory, copy/move, rename and final placement, followed by
nonrecursive removal of that empty staging directory. This avoids colliding
with unrelated source-named files at the destination. It is not atomic; a moved
source can temporarily live under the reported staging path. Every step is
recorded and an ambiguous synchronous response also blocks replay.

`status --operation` only observes the recorded task, even with `--wait`. If a
staged operation has another write step, it returns `continuation_required` and
the original command to resume. This preserves the read-only meaning of status.
An operation cannot silently resubmit its earlier task.

The issue's dry-run wording both prohibited reading secrets and required usable
existing authentication. The implemented interpretation permits loading a
saved session from its credential store for bounded preflight. It forbids
prompting, refreshing auth, saving configuration/cache/operation state and
submitting mutations. It neither reads a new sharing password nor requires
confirmation. The CLI guide states this boundary explicitly.

## Rejected alternatives

Using only HTTPS would leave the required interface/disk/service outcomes
unimplemented. Undocumented DSM management APIs would weaken the version and
permission contract. Enabling SSH/SNMP as part of login would turn read-only
onboarding into NAS administration. Reusing global mutable row numbers would
retain a cross-process target-selection race. Retrying an upload or task without
its response would guess that the first submission had no effect.

The chosen adapters add optional dependencies and expose partial results more
often. Staged rename adds durable state and a visible intermediate directory.
Those costs are preferable to inventing device health, implicitly broadening
NAS permissions or treating an ambiguous write as a confirmed failure.
