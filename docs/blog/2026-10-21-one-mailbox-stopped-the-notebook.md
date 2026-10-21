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
