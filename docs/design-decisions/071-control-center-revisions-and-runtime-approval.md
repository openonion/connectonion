# DD071 — Control Center revisions and runtime approval

Status: implementation candidate for 1.8.4 / #1354; not deployed or released.

A Control Center is a complete static build. The authored project proposes its
bytes; a Host-owned update operation decides whether to activate them. A boolean
`approved` in a project file or model reply is not an activation capability.

## Complete revision and hosting

The `connectonion.control-bundle/1` manifest identifies every file by path, byte
size, SHA-256 and a fixed MIME type, plus entrypoint and requested capabilities.
Canonical JSON uses sorted keys, ASCII escapes and compact separators. The
revision is the manifest's SHA-256. Core captures immutable byte objects before
review. API upload independently verifies the same manifest and all file bytes.
The shared fixture is `tests/fixtures/control-center/bundle-v1.json`.

The existing oo-api owns authenticated outbound upload and GCS reservations.
Static content is served by a separate ASGI process on an explicitly configured
separate registrable domain. A base32 hash of account, app ID and revision names
its origin. Every revision therefore has independent storage and service-worker
scope. This works when the Agent is behind NAT or reachable only through Relay:
assets do not travel over the Agent connection.

Limits are 256 files, 20 MiB total, 8 MiB per file; public paths exclude hidden
files and traversal. An account has at most 100 reserved revisions/200 MiB.
Generation checks prevent concurrent quota bypass and immutable overwrite. The
origin manifest is written last. Failed partial uploads retain quota reservations;
retrying the same revision is idempotent. No automatic expiry is promised: objects
remain until explicit operator takedown. Rollback checks availability again.

An authenticated upload is storage permission, not review approval. Only the
Host's active descriptor connects that URL to its reviewed Agent experience.
Bare public app URLs receive no identity, private chat history or Agent authority.

## Review and activation

`SkillReviewer` snapshots the packaged `control-center-review` skill and includes
its content, model and resource limits in the policy ID. Each review uses a fresh
Agent subprocess, with no tools, author history or callbacks. It receives the
captured manifest and complete executable source, including WASM as base64.
Non-executable binary assets remain identified by hash. Executable source is
bounded at 512 KiB, output at 4096 tokens, one call with no provider retries,
and 90 seconds wall time. Builds exceeding the review budget are blocked rather
than silently truncated. This candidate supports production builds that fit that
budget; arbitrary-size framework applications need a separately designed review
strategy.

The model may return only schema, exact revision, status and findings. The
runtime supplies review ID, model identity, execution ID, policy, timestamps and
reported cost. Blockers cannot coexist with approval. A reported cost above
$0.25 blocks activation; this is a post-call activation limit, not a promise that
a provider can undo already incurred billing. Source edits during review or
upload require a fresh attempt. Failed or malformed review and upload preserve
the previous approved pointer. The bytes actually uploaded are the captured bytes.

Runtime state lives outside the authored workspace and is authenticated with a
private runtime key. Project-written receipts are never read. The deployment
must keep that state root/key outside author-tool filesystem authority. This
protects the application protocol and workspace boundary; it cannot defend
against an operator or arbitrary same-user native code that can read the runtime
key. OS-level separation is required when author execution has that authority.
One OS lock serializes updates and rollback. Retained signed approvals, the
current policy ID and artifact availability determine rollback eligibility.

## Browser contract

The full app is an ordinary cross-origin iframe, without a feature-limiting
sandbox. The serving CSP allows local/inline scripts, production framework
chunks, local Workers, WASM and HTTPS/WSS data APIs. Mutable external code and
JavaScript eval are blocked. Bundle code dependencies into the reviewed revision.
Data refresh does not regenerate code and does not invoke review.

The parent owns the authenticated SDK connection. Bridge operations must be
visible, attributable chat turns; initial snapshots and ordered updates come
from the same SDK state. Embedded, focused and new-tab O Chat shells must use
the same approved revision. The bare static URL has no implicit session.

## Update and validation work

Manual, periodic and internal-event updates must use this same review operation.
The Host's existing minute tick and calendar/interval calculation are reused;
durable control state must show paused/enabled, next run, last attempt/success,
error and revision. Event IDs require retention/deduplication, coalescing and
loop prevention. No external mail-delivery scheduler is added by this work.

The initial Core bundle/review/upload/activation suite passes 40 synthetic tests.
The companion hosting suite passes 12 tests plus eight existing image-origin
regressions. Live review export, GCS/proxy/TLS deployment, full bridge browser
acceptance and the eventual coordinated artifact tests remain separate evidence.

### Implemented Host update controls

`CONTROL_CENTER_COMMAND` is a signed application command on the existing direct
or Relay connection. It supports state, update, configure, source, diff and rollback.
Only verified Host administrators may author/configure/read source or roll back;
trusted connected users receive the active descriptor and redacted review state.
A control command returns a correlated result. Starting an update acknowledges
its durable claim immediately; state pushes report its later outcome. Losing
the UI socket does not cancel a claimed background update.

The Host injects `update_control_center` into configured Agents. It requires the
server-owned administrator requester and uses the same durable attempt budget
and review gate. It never accepts a filesystem path or author-provided receipt.
`co create` supplies the build; default `co init` remains global-only.

Update settings persist outside the project: enabled/paused, interval (60 seconds
to seven days) or daily HH:MM with IANA timezone, internal event subscriptions,
and debounce (0–300 seconds). The Host's existing minute tick and OS tick lock
run these updates, including without Relay or an ordinary schedule.yaml entry.
After downtime, at most one due run is performed; there is no replay burst.
Initial events are completed Agent turns, completed explicit slash-skill turns,
and detected source changes. Deduplication retains at most 1024 IDs for seven
days. A pending batch coalesces, with a five-minute maximum debounce; the
Control Center's own generated turns and already-active source are excluded.

A separate authenticated queue lock admits events while the runtime writer is
reviewing. Live process ownership prevents a second worker from generating;
an interrupted process is recorded for manual retry. The default daily bound
is 24 attempts (configurable 1–96) and $2 reported cost. Author turns are bounded
at eight iterations; between calls a five-minute/$0.50 guard stops further work.
An in-flight provider call may finish after that guard's deadline; the gate
cannot undo provider billing. Review has the separate subprocess wall deadline.
Failures wait for the next configured occurrence or an explicit retry.

Targeted Host, schedule, profile, session-sync and Relay regressions passed 221
tests before the final cross-repository build. Full-suite evidence is pending.


### Capture and recovery boundaries

On POSIX, capture pins every ancestor and descendant directory with descriptor-
relative opens and rejects symlinks. Renaming an ancestor cannot redirect a file
read outside the chosen build. Windows uses bounded regular-file checks; operators
must prevent concurrent untrusted writes to build ancestors there. This is a
filesystem boundary, not a sandbox for the normal author Agent's tools.

The authenticated history is bounded by count and encoded bytes. Pruning preserves
the latest attempt and the active revision's latest approval. Code view retrieves
retained source without credentials from its immutable origin and verifies size
and SHA-256 against the recorded reviewed manifest; display limits are 128 KiB per
source file and 256 KiB per diff. Missing/taken-down artifacts fail explicitly.
An interrupted update remains paused across later ticks until manual retry.

The starter now uses the same browser SDK entry point as framework apps. Its local
copy includes a version/hash record and the SDK license; ordered snapshots include
normalized ChatItems, live connection state and published skills. The parent limits
snapshots and flags omitted history. Request cancellation is scoped to the app's
own pending idle-started turn. Bare URLs do not receive a port or identity.

## Final coordinated acceptance

Core `909798b5` passes 8,318 tests (23 skipped, 184 deselected). Commands on
legacy sockets independently verify the signed inner payload. Unchanged builds
are re-reviewed after a policy change. React, O Chat, hosting, installed-artifact
and nine-case browser evidence is recorded in
[the acceptance record](../acceptance/1.8.4-control-center.md). A live synthetic
review approved the fresh-process model path; deployment remains separate.
