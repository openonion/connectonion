# The request ended. The copy did not.

The copy test lost its connection just after the NAS returned a task ID. The
client had reached its waiting limit. The NAS still had a job to do.

An ordinary exception would have made the next instruction easy to write:
retry the copy. It would also have discarded the most useful fact in the
response. We knew which job had started. Starting another job was a different
action from waiting for that one.

This happened in a synthetic fixture while implementing the Synology core for
ConnectOnion 1.8.4. It was not a successful transfer on a real NAS. The fixture
let us put the interruption between two precise events: receiving a task ID
and receiving a completion result. That distinction became the design.

The first version of the Synology tool had a much smaller job. It listed files,
searched, transferred bytes and produced sharing links. Its status method made
a File Station request and reported that the connection worked. The expanded
core asked for network, storage, disk and service inspections as well as safer
file operations. A longer list of command names could have hidden both gaps:
missing inspection evidence and uncertain writes.

We started by separating the sources. A verified HTTPS request can report the
client's endpoint, its timing and File Station access. It cannot tell us whether
an interface is down. A disk's deployment status cannot substitute for a health
field that the NAS did not report. An API name cannot establish that a service
is running.

The inspection fixture makes that visible. One disk has a normal deployment
state and no health indicator. Another has a critical health indicator. The
first stays unavailable for health. The second stays critical. Neither gets
folded into a friendly connection check. A separate aggregate fixture supplies
a degraded storage row and a down interface, then verifies that both become
warnings while the missing disk-health field keeps coverage partial.

The source choice has a cost. File Station handles verified HTTPS identity and
file access. Optional SNMPv3 reads the documented interface and device counters.
Optional SSH enumerates services with fixed read commands and a configured key
and known-host file. Someone who configures only HTTPS will see unavailable
checks. We chose to show that gap. Automatically enabling another transport, or
using an undocumented management endpoint, would turn a read-only inspection
into a different product promise.

File operations presented the same problem in a less visible form. A command
can recognize a request, and even send it successfully, without knowing its
outcome. The test with a returned task ID now saves the operation and reports
that it is pending. A new process can ask for the status of that same ID. The
regression checks the outgoing method names: the follow-up makes status calls,
not another start call.

A second fixture loses the response earlier. There is no task ID to save. This
case becomes `submission_unknown`. Repeating the same copy command finds the
saved uncertainty and does not submit it again. The test counts one request
across both invocations. The record does not prove that the NAS copied anything;
it prevents the client from pretending that a lost response proves the opposite.

Renaming exposed another tempting shortcut. The documented CopyMove API accepts
a destination folder. It does not accept the arbitrary destination filename in
our CLI example. Copying into the destination folder and renaming afterward
could collide with an unrelated file bearing the source's original name. Moving
the source first would make the failure harder to recover from.

We used a unique staging directory for that case. The workflow records the
staging path, the transfer into it, the rename, final placement and removal of
the empty staging directory. Each write step is recorded before submission.
That is more state than a single API call. It also means a moved file can
temporarily live in the staging directory if the command is interrupted. The
result says where it is expected to be; it does not call the workflow atomic.

There was a choice about what `status --wait` should do when the transfer into
staging finished. Letting status perform the next rename would make the workflow
feel seamless. It would also make a status command submit a write. We kept
status observational. It reports `continuation_required` and supplies the
original command to resume the recorded workflow. Another regression checks
that the status path sends no rename or new task request.

Downloads needed a different boundary. Their temporary file is local, so we
can preserve the old destination until the byte stream and available length
evidence agree. One fixture starts with old bytes, supplies a short response,
and verifies that the old bytes remain after failure. Another downloads an
empty file and verifies the hash of those zero bytes. The output identifies
that hash as evidence about downloaded bytes; the NAS did not supply a server
hash for us to compare.

These tests do not remove every race. File Station does not provide the
compare-and-swap primitive needed to guarantee that a remote path stayed
unchanged between preflight and transfer. The Windows implementation also lacks
the POSIX ancestor-descriptor protection used for local placement. The live
NAS/model acceptance matrix is still empty in this task. Those limits belong
beside the implementation, not behind a successful parser test.

The useful result is a narrower statement at each boundary. A configured source
may be unavailable. A finished request may leave a pending job. A lost response
may leave an unknown write. A completed staging task may still need an explicit
continuation. Once those states had names and saved evidence, the next command
could follow what we actually knew.

Implementation details and current evidence are recorded in the
[Synology decision](../design-decisions/070-synology-inspections-and-durable-operations.md)
and [acceptance record](../acceptance/1.8.4-synology.md). This is a candidate
implementation, not a package release announcement.

## A returned link was not proof of its settings

A sharing regression exposed the same boundary. Its fake NAS accepted a create
request, then returned a link with password protection disabled. The client had
been filling the result from the request, so it could describe protection that
the returned link did not have.

Creation now reads the link back before returning it. The regression supplies a
matching link ID and path but the wrong protection flag. The client revokes only
that identified new link and reports a failure. If the identity does not match,
it cannot safely choose a link to revoke. If readback or cleanup is uncertain,
it names that uncertainty and asks for inspection before another create call.

The fixtures also distinguish a missing expiry field from an explicit no-expiry
value. Empty-string and zero sentinels normalize to no expiry; missing metadata
cannot certify the requested settings. A settings check still cannot prove that
a browser enforces a password or that an in-flight download stops on revocation.
Those are separate acceptance questions, just as a returned task ID is separate
from a completed copy.
