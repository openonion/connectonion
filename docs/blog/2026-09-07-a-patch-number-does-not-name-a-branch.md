# A patch number does not name a branch

The 1.8.4 readiness review found a pull request aimed at `main` failing a
forward-port check. Its proposed version contained a nonzero patch number, so
the workflow demanded an open issue promising to carry the change to a higher
line. But the change was already headed to the newest line. Creating an issue
would satisfy the expression while making the release ledger less truthful.

The original check protected a useful rule. A fix on `release/1.7` must reach
the active higher lines before that work is considered finished. The mistake
was treating a version string as the destination branch. We kept the open-issue
and label checks and narrowed their trigger to maintenance branches. Mainline
and feature stacks still require a release estimate; they do not invent a
forward-port obligation. If a future maintenance branch uses another naming
scheme, the policy and regression fixtures must change together.

The regression executes the workflow's actual JavaScript with synthetic PR
events. It covers mainline 1.8.4, preview and stacked work, missing metadata,
and maintenance trackers that are absent, closed, unlabelled or valid. This is
a proposed process correction. It does not merge a feature, close an existing
release ledger, or publish 1.8.4.
