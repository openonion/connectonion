# REM init investigation fixes (unreleased)

Init investigates eligible people, queued projects, related organizations and
installed skills, with recent work first. The existing caps still let the user
limit each kind. A wider map refreshes retained project messages against its
new folders, so older projects are not stranded behind an extraction cursor.
Mapped projects with readable local files are also investigated when no typed
session messages were retained. Missing or deleted folders do not count as
investigated evidence.

Skill reviews compare installed instructions with retained eval records and
up to three matching invocation turns. They also read linked Markdown, text
and XML references inside the skill's own folder, up to 1 MB total. Links to
other folders, hidden paths and symlinks are excluded; omitted references are
reported as unreviewed. Reference instructions establish intended behavior,
not successful execution. Large records are searchable, lossless
numbered parts. Promotion preserves citations to their exact original record
IDs, mapped source provenance and invocation counts. Optional empty sections
are omitted; a cited Insight leads the skill page.
Refreshing collected run evidence repairs duplicate collector-owned sections,
including pages whose model review dropped the surrounding markers.

Indexed task packets explicitly allow reading their evidence bodies. The
no-reread instruction applies to the already-inline packet files, not the
indexed archive. Person investigations survey relationship threads across
dates, preserve original provenance, and check later replies before naming
open obligations. Meeting dial-ins are excluded from automatically restored
contact phones, including older flattened Zoom invitations.
Before declaring nothing open, person reviews check requests and promises
across topics: an unrelated recent reply does not close an earlier request.
Skill pages use notebook links rather than copying source-relative links.
If a source typo would erase a lead, Insight, Current status or Open threads
finding, promotion gives the candidate one citation repair turn. A second
failure preserves the original page; both turns' usage is counted.
Temporary directory roots are excluded as well as their descendants. Known
Facts labels without list markers are normalized before missing fields become
Unknown, so their cited values appear in the reader's summaries. Invitation-only
evidence cannot establish completed obligations. Skill reviews without runs
look for a source-specific default, boundary or conflict and its consequence.
Zoom detection avoids retrying an unbounded subdomain match at every character
of a long mail body.

Historical Codex windows support older native headers. Legacy messages retain
their session-start date with an explicit note that individual message times
were not recorded. Current native messages with a null metadata passthrough
and no optional id are recognized using the existing speaker and injected-text
filters. Older interactive native CLI messages whose metadata only records
`turn_id` also retain their typed requests. That compatibility requires native
interactive CLI metadata; an exec wrapper or Desktop import does not qualify.
Subagent messages and imported Desktop history remain excluded, and
the skill-usage cache is recounted under the corrected reader. Investigation
coverage reports unfamiliar user-slot formats instead of silently omitting
them. Full-window gathering uses larger read batches to avoid repeatedly
hashing the same large transcript prefixes; the evidence window is unchanged.

These changes address #2133, #2135, #2136, #2137, #2138, #2143, #2144, #2149, #2150, #2151, #2152 and #2154. They do not establish
that every generated insight is useful or that a reported skill outcome was
independently verified. Live page review is still in progress; no package has
been published for these changes.
