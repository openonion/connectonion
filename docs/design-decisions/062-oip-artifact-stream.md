# DD-062: Browser files use one OIP Artifact Stream

Status: accepted for the local BrowserDaemon boundary; remote carrier pending
the reviewed OIP secure-channel profile and conformance vectors

## Decision

Browser files are streams attached to Browser command transactions. They are
not command text, base64 data URLs, public URLs, or paths on the daemon's
filesystem.

The caller still performs one operation:

```bash
co browser take_screenshot
co browser take_screenshot --out ./evidence.png
```

The command captures the browser output, transfers it, verifies it, commits it
on the caller's filesystem, acknowledges it, and removes daemon staging before
reporting success. Remote Browser will use the same logical records when its
secure OIP carrier is ready; it will not introduce a `get` command or a base64
fallback.

## Contract

New BrowserDaemon clients send a length-delimited Protocol Buffers `Envelope`
with typed `BrowserCommand.argv`. Text results, errors, stream metadata, stream
data, completion, and receiver commit all use that same envelope.

```text
BrowserCommand
BrowserResult(artifact_count=N)
StreamOpen
StreamData ...
StreamFin
StreamCommit(receiver)
StreamCommit(sender confirmation)
```

The receiver commit says that the verified caller file is durable. The sender
then removes its staging file and echoes a sequenced `StreamCommit`; only that
confirmation lets the client report success. This makes the ownership handoff
observable instead of depending on scheduler timing.

The checked-in schema is
`connectonion/network/oip/browser_daemon.proto`. The current local carrier uses
the `OIP2` preface to distinguish new frames from the bounded wire-v1 migration
reader. A new client never emits wire v1. Artifact transfer has no legacy
fallback.

The first profile limits one `StreamData` payload to 256 KiB. A file may contain
any number of frames allowed by the caller's configured resource policy and
available storage. This keeps a memory-safety message bound without turning the
old 1 MiB command-message guard into a file-size limit.

## Ownership boundary

Browser Core writes only into a private, per-request daemon staging directory.
The daemon proposes a safe display name and streams the bytes. The caller:

1. chooses the local destination;
2. creates a mode-0600 partial file;
3. accepts only contiguous stream IDs, sequences, and offsets;
4. verifies declared and observed size plus SHA-256;
5. atomically exposes the partial file without replacing an existing name;
6. sends `StreamCommit` containing the verified size and digest.

The daemon removes staging only after the transaction reaches the commit
boundary or terminates. Caller-supplied output paths never cross to the daemon.
Daemon-proposed names cannot escape the caller's output directory, and an
existing local file is never overwritten silently.

For screenshots this also changes the AI path. The daemon no longer sends a
base64 image to `DaemonBrowserProxy`; it sends the same artifact stream and the
proxy receives `Screenshot saved to: <caller path>`. The existing image-result
formatter reads that caller-owned file for the model.

## Downloads

The stream primitive is ready for downloads, but accepting Chromium downloads
is not itself a download API. Browser Core still needs an explicit capture
operation that arms the selected tab's download event, performs the approved
action, waits for completion, registers only the completed regular file, and
then invokes this same Artifact Stream.

Download security requirements are:

- a dedicated Browser capability rather than Bash or arbitrary filesystem read;
- caller/request/tab binding from authenticated transport context;
- regular files only, no symlink traversal or caller-selected daemon path;
- sanitized proposed names, collision-safe caller commit, and no automatic open;
- configurable size, disk, time, concurrency, and retention quotas;
- content remains untrusted and may be quarantined by platform policy;
- incomplete transfers leave no visible final file.

The download feature must not add `download get`, presigned URLs, shared mounts,
or inline base64. It produces the same `StreamOpen` → `StreamCommit` sequence.

## Remote transport and authentication

Local IPC is authenticated by its platform boundary: a private Unix socket on
POSIX or the existing authenticated named pipe on Windows. The Protobuf envelope
does not itself create remote authenticity or confidentiality.

Remote Browser Artifact Stream remains disabled until the #1208 secure-channel
work selects a reviewed protocol/library and publishes deterministic positive
and negative vectors. The remote profile must bind caller and recipient Agent
addresses, roles, selected capabilities, endpoint, freshness, and record
counters into an authenticated transcript. Direct TLS remains defense in depth;
Relay must see only the routing data and ciphertext it needs to forward.

We will not invent Browser-specific encryption or ship plaintext artifact frames
over the Relay to make a preview date.

## Resume and command outcome

The local foundation completes a stream on one connection. The remote profile
must add a durable command journal before automatic resume is enabled. Retrying
the same authenticated request ID resumes its recorded streams and never repeats
a browser side effect.

If the Host crashes after an external browser action but before it can durably
record the result, the only safe response is `COMMAND_OUTCOME_UNKNOWN`. The
client must not automatically execute the action again.

## Alternatives rejected

- **Base64 in JSON:** adds roughly one-third overhead, forces complete-file
  buffering, and converts message limits into file limits.
- **Return the daemon path:** works only on a shared filesystem and exposes an
  authority the caller does not possess.
- **Run `get` after every command:** creates two public operations, two failure
  models, and leaked remote retention when the second step never runs.
- **Presigned or public URLs:** add a bearer capability, storage service, expiry
  race, and separate authentication path.
- **Remove all limits:** confuses file size with frame allocation. Files should
  stream under explicit resource policy; individual messages must remain
  bounded against memory exhaustion.

## Evidence required for promotion

The local preview gate includes multi-frame files larger than 1 MiB, malicious
offset/hash/name cases, no-overwrite behavior, real Unix-socket round trips, and
the existing BrowserDaemon concurrency suite. Remote promotion additionally
requires secure-channel vectors, direct and opaque-Relay carrier conformance,
resume without duplicate action, cancellation/backpressure, large downloads,
host restart, cross-caller isolation, and malicious filename/content fixtures.
