# The Wiki worked, but the small input was not cheap

The request was to check the PR and see whether it could actually organize
notes. The first surprise was that the work was split: #1448 held the
foundation and #1454 stacked the real runner, scheduler, and local reader on
top. Testing only the foundation would have answered the wrong question.

The latest branch passed 135 focused offline tests. GitHub's older Python
jobs still failed during import. `Notebook.list` was being used as the
`list` in another method's return annotation. Python 3.14 deferred that
evaluation, hiding the error locally. Resolving the type hints reproduced it;
postponing annotations fixed it. That small foundation fix was merged into
the follow-up branch without flattening the two PRs.

Then came the real test. An isolated Codex session said Aurora would keep
Markdown for portability. The Wiki created a project and a decision. A later
session corrected the reason to inspectability. The existing decision changed,
SQLite remained a rejected alternative, and another sync with nothing new
made no model call. A separate Codex used the Wiki to answer a question. The
whole CLI journey, including start and stop, passed in 77.89 seconds.

The run journal was less reassuring than the pages. The two maintenance
batches took 25.4 and 21.4 seconds and consumed 177,772 input tokens, including
151,040 cached input tokens, plus 6,139 output tokens. Those figures did not
include the test's separate tell and ask calls. A small message count did not
mean a small model workload. The notebook was useful; making that workload
predictable remained unfinished.

The reader needed no service: Chrome opened the generated file directly.
Links and search worked, source markup stayed inert, and the 375px viewport
had no horizontal overflow. The browser made no HTTP requests. Finally, a
real launchd interval served a saved slot after about five minutes, and stop
removed the test job. That check used empty sources and spent no model tokens.

These results justify moving the implementation forward, not declaring every
boundary solved. The tests used synthetic sources, the scheduler was exercised
on one Mac, and the hostile-source check proves its specific assertions, not
that arbitrary private reads are impossible. Both PRs remain drafts while
compatibility CI and cost work catch up with a now-working core loop.
