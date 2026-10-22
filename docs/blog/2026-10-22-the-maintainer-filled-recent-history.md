# The maintainer filled recent history

*2026-10-22*

A user opened their recent Codex work and found maintenance conversations among
it. REM writes one page per model call. Every call had become an ordinary saved
conversation, so a notebook catching up on many pages could push the user's own
projects out of view. The background work was doing its job, but its traces
were competing with the work the user came back to do.

The first proposal was to replace REM's clock with Codex App Scheduled. That
would put the recurring task in a familiar place and remove another clock to
maintain. Inspection exposed two separate problems: the installed App Server
protocol had no schedule-management method, and changing the outer trigger
would still leave all the inner REM calls as ordinary conversations. Writing
the desktop application's legacy automation files was not evidence that its
current scheduler had accepted the job.

We worked on the conversations first. Codex already has thread archival, so REM
can keep a trace without leaving it in active history. A local Pro trial made
that distinction concrete: after archive, the ID disappeared from active
`thread/list` results and remained in archived results. The trial used an
invented memory word in a temporary directory; it did not read a mailbox or the
owner's notebook.

The next step failed. `thread/resume` refused the archived ID. Saving a trace
was not enough to make it resumable. REM now unarchives the same ID before
explicit resume and archives it again afterward. Two calls through the actual
Python adapter retained the invented word, returned the same ID, and left the
thread only in archived results. A listing that scanned the whole local history
hit a 15-second deadline; the final trial queried the native state database.

Independent AI review found another failure path: an archive error could escape
cleanup and hide the call's result. Archival now sits inside the adapter's
existing error boundary. A simulated archive failure returns the thread ID,
available message, usage and original turn status alongside the error, and
still closes the client. Cancellation or process death can still leave an
active trace; this change does not sweep away existing history.

The candidate therefore makes a smaller claim than the first proposal. It
addresses internal conversation clutter, preserves explicit resume, and leaves
launchd scheduling unchanged. Native Scheduled adoption needs a verified
integration and a separate test that the task really fires. The native desktop
sidebar also remains an inspection gap: the live evidence here is the provider's
active and archived lists, not an all-page UI pass.

See the [acceptance record](../acceptance/rem-codex-history-2026-10-22.md) and
[candidate notes](../releases/1.9.3rc13.md). Publication depends on the release
checks; a locally working candidate is not a published package.

A follow-up native registration probe kept that boundary honest. It created one
paused legacy definition, then a one-shot whose only effect was writing an
isolated marker. After 190 seconds (100 seconds past its scheduled time), the
running desktop installation had no registration for its ID, no run record and
no marker. The probe and its temporary directory were removed. This does not
show that native Scheduled is broken; it shows that writing an old-format file
is not a validated integration here. The [native probe record](../acceptance/rem-native-scheduled-2026-10-22.md)
keeps that result separate from the successful archive/resume trial.

Reading the creation and load paths changed the next step. The desktop bundle
has its own storage and clock; the public CLI tree only carries a dynamic-tool
example for `automation_update`. Running the installed storage functions against
a temporary home proved that a valid legacy TOML can rebuild its missing SQLite
index. Writing both stores is what creation does, but it is not a universal
requirement for loading a task. A separate capability flag gates the actual
clock. In migrated mode the canonical definition is saved remotely and then
cached locally; synchronization removes an owner-scoped row that was never
registered there. The [source-level checks](../acceptance/rem-native-source-2026-10-22/README.md)
therefore show a path to reuse native structures, rather than a reason to build
another scheduler. They still do not certify the running desktop's model-turn
execution: the isolated tick test replaced that last boundary with a marker.

The candidate also raises its minimum Python version to 3.11 and its Pillow,
pypdf and cryptography security floors. Keeping Python 3.10 and an old Intel
Mac wheel pin would retain vulnerable dependencies. The tradeoff is explicit:
Python 3.10 users need a supported interpreter; Intel Macs need build tools
for cryptography because upstream no longer supplies Intel wheels. This is
separate from native scheduling, whose live acceptance has not passed.
