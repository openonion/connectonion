# A red check nobody caused

A pull request that changed two functions in the notebook's prompt
composition failed CI on a job it could not have touched: `lockfile`, the
check that our dependency lock matches `pyproject.toml` and that nothing in it
has a known vulnerability. The lock matched. The vulnerability was new.

Overnight, three advisories had been published against urllib3 2.7.0, the
version our lock pins, fixed in 2.8.0. Nothing in the repository had changed.
The world had, and the audit noticed.

That is the audit doing its job, and it is also why the failure landed on
whoever pushed next. Every open pull request would now go red on the same
job, each author would look for what they broke, and none would find it.

The fix is two lines: the published floor in `pyproject.toml` moves to
`urllib3>=2.8.0`, and `uv lock --upgrade-package urllib3` moves the lock with
it. We keep that floor in the published metadata as well as the lock, because
the lock protects this repository but is not installed with the library. A user who
already had 2.7.0 installed would otherwise keep it when installing
ConnectOnion.

The same audit, run locally with the pinned `uv` and `pip-audit` versions, now
reports no known vulnerabilities. It is a small change landed on its own, so
the pull requests stuck behind it go green again for the right reason.
