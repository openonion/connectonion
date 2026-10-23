# One mailbox stopped the notebook


A saved REM run ended before its first model call because the authorization
service could not be reached. Preserving its credentials and source cursor was
correct. Returning from the entire source loop was the product mistake.

The real log establishes that one pass failed. It cannot establish that another
source had unread work. A synthetic regression supplied that missing condition:
an unavailable mailbox first, a valid and consented local session second. The
maintainer never received the session. With the proposed repair, it does.

We considered retrying the mailbox immediately, switching its provider, and
continuing the selected sources. Continuing selected sources is the narrow repair:
it preserves consent, the existing rotation, daily limits and one source kind per
batch. It does not change credential refresh semantics. A run with accepted work
and an unavailable source says partial, not caught up. A total collection failure
costs no model call, and backfill stops rather than looping over the failure.

This is candidate behavior for a future reviewed preview. Tests use synthetic
material and trusted fake maintainers. They establish orchestration, not recovered
mail access, correct generated memories or a successful real overnight run.

On 23 October, integrating the repair with rc16 exposed the reader's side of the
same contract. It treated partial as quiet and could announce no change despite
unread sources. The candidate now shows attention while retaining accepted work,
separates partial from fully failed runs, and links to the exact run log without
printing private provider errors. Five logical reader cases failed before this
correction. They do not replace current native desktop, phone or accessibility
acceptance, which remains pending.

Independent AI review found a further mixed-failure boundary: a source could fail,
healthy material could continue, then the model could fail in the same run.
Suppressing all model diagnosis whenever a source error existed hid that second
problem. Three service-to-reader regressions failed for authentication, quota and
timeout before retaining the failed model stage and both generic recovery reasons.
Source-only errors still do not imply model access failure; private output is not
echoed into the brief.
