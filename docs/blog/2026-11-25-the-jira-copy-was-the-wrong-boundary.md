# The Jira copy was the wrong boundary

The Jira draft could read a selected issue and save it locally. Repeating the
same import appended no duplicate record. That was useful evidence for the
export path, but it did not answer the question the maintainer asked next:
how should REM read a source?

The first implementation answered with another local pipeline. It connected
a scope, wrote daily JSONL snapshots, mapped identities, and taught generic REM
code about Jira at several points. Each step looked reasonable alone. Together
they meant that adding Jira changed the service, runner, investigation and map.
Meanwhile upstream kept moving. Updating the draft brought conflicts in CLI
registration, REM help and the service, exactly where that coupling lived.

Issue #3249 changed the boundary. A source is a command. REM asks what changed
and reads an item when it needs it. The later owner clarification went further:
REM should not preserve another source store or promise an old saved version.
A citation points to the live issue, and a missing or changed issue must be
reported as such.

This revision therefore gives Jira two live reads. `changes` requires a selected
project and accepts named issue keys to narrow it further. `show` reads one
explicit issue key. JSON stays on stdout; recovery and next commands go to
stderr. The old Jira-specific snapshot wiring is removed from generic REM.
Maintainer review also removed the manual export and checkpoint machinery from
this PR. The surviving source boundary reads live and stores no source copy.

The important test is no longer whether the second import appends zero lines.
It is whether a changed issue appears within the selected scope, whether a
cross-project result is refused, and whether a failed page or rate limit avoids
claiming a complete list. The new synthetic tests exercise those boundaries.
They do not establish live Jira acceptance or prove that every nightly stage
consumes the commands; those still require the revised branch's user journey
and the generic REM audit.

The lesson is that a correct export is not automatically the right integration.
Once the command is the boundary, provenance can stay explicit without making
each source another storage and lifecycle subsystem inside the notebook.
