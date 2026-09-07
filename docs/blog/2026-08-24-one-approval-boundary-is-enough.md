# One Approval Boundary Is Enough

The second RC3 gate reached the exact state we wanted to test: the outer Host
had dropped from Full Access to Auto, and an open Codex Work Room had already
shown the narrower profile. The next task explicitly asked for Claude Code.
The parent agent announced the delegation, then waited for five minutes without
starting Claude.

Claude Code was healthy. Calling the same candidate adapter directly returned
the expected marker with exit code zero. The wait belonged to a redundant
outer approval that the release harness could not see.

`co ai` deliberately gives its Codex and Claude Code wrappers a session-local
grant. Those wrappers start managed native runtimes whose own permission
profiles govern file and command actions. Asking once more before entering the
wrapper does not add a useful boundary; it only hides the provider's real one.

Auto's deterministic classifier did not know about that narrow grant. It
classified the wrapper name as unknown, required a person, and then discarded
every reusable permission except one whose source was `user`. The managed grant
used the truthful source `safe`, so a policy intended to prevent broad config
from bypassing approval also filtered out the capability `co ai` had just
created.

The fix does not put Codex or Claude Code on a global allowlist. Auto recognizes
only the exact session grant injected by `co ai`: supported provider name,
allowed flag, safe source, managed-delegation reason, and never expiry. It
records that call as an allowed managed delegation. Config grants, near matches,
arbitrary safe reasons, and incomplete grants remain unknown and still ask.

Tests now run the deterministic Auto classifier and the human approval hook in
their real order for both wrappers. The lesson is that nested approval systems
need one explicit handoff point. Duplicating the outer dialog does not make the
inner runtime safer; it makes the authority model harder to observe and test.
