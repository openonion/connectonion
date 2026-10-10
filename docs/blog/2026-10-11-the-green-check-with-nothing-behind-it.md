---
description: help-gate's model review ran out of credit and still showed green. Advisory is fine; silent is not. The job now says when no verdict was produced.
tags: [CI, CLI]
---

# The green check with nothing behind it

Every PR that touches the CLI gets two kinds of help review. The hard rules
(an example on every page, a way back, real flags) run in the test suite and
block the merge. The second kind is a model reading each changed page and
judging whether it is clear and simple. A model's verdict varies from run to
run, so that half was made advisory: it writes to the job summary and never
blocks.

The line that made it advisory was `co audit ... --review || true`.

## What `|| true` swallowed

On PR #2238 the CI account had $0.0006 left and the review needed $0.0054.
`co audit` raised `InsufficientCreditsError` and exited 1. `|| true` turned
that into exit 0, and help-gate went green. Anyone glancing at the PR saw a
passed review. There had been no review.

`|| true` was meant to say "a bad verdict should not block". It also said "a
crash should not block", and there was no way to tell the two apart from the
outside. Both exited 1. Only one of them had read anything.

## Telling them apart

A finished review always ends with a verdict line, either "fit for an agent
harness" or "not yet fit". A crash ends with a traceback. The step now keeps
the output, looks for that line, and if it is missing, titles the summary
"review unavailable, no verdict was produced" and puts a warning on the
check. It still never blocks. It just no longer claims something that did
not happen.

The test runs the workflow's own bash step against a fake `co` that dies the
way the credit error did, so changing the YAML is enough to make the test go
red.
