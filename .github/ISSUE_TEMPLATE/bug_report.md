---
name: Bug report
about: Create a report to help us improve
title: '[BUG] '
labels: 'bug'
assignees: ''

---

## Describe the bug
A clear and concise description of what is broken.

## Release planning
- **Affected ConnectOnion version:** [e.g. 1.7.0a3]
- **Suggested target version:** [e.g. next patch, 1.8.0, 2.x, or TBD]
- **Estimated release window:** [e.g. urgent patch, next alpha, future roadmap, or unknown]
- **Why this priority:** Explain the user impact and whether a workaround exists.

> The reporter's target is an estimate. Maintainers confirm the release by assigning a milestone.

## To reproduce
1. Install ConnectOnion version '...'
2. Run code '...'
3. See error

## Expected behavior
A clear and concise description of what you expected to happen.

## Code example
```python
from connectonion import Agent

# Minimal reproduction
```

## Error output
```
# Paste the full error traceback here
```

## Environment
- OS: [e.g. macOS, Ubuntu, Windows]
- Python version: [e.g. 3.10, 3.11, 3.12]
- ConnectOnion version: [e.g. 1.7.0a3]
- OpenAI API key configured: [yes/no]

## Additional context
Add any other context, screenshots, or examples.

## AI implementation contract

<!-- The bug-sized subset. Full guidance, repository defaults, and
     guardrails: docs/ai-implementation-contract.md -->

### Scope and release line
- Target: [ ] stable patch [ ] preview [ ] main-only
- Exact base/tag:
- Owning repositories:
- Explicitly out of scope:
- Release action authorized by this issue:
  [ ] test only
  [ ] prepare Draft release PR
  [ ] publish approved Preview
  [ ] publish stable
  [ ] no publication

### Plan before code
- Reproduce first: a regression test must fail on the unpatched code before
  the fix has any claim to work.
- Inspect the current implementation, tests, and related PRs/issues before editing.
- Do not merge a preview `main` wholesale into a stable branch.

### Required verification
- Focused red/green regression test:
- Full suite on the exact candidate commit:
- Real journey exercising the fixed path (browser/CLI as applicable):
- Commands and exact output to record:

### Evidence
- [ ] The regression test's red run (pre-patch) is recorded in the PR.
- [ ] Before/After behavior is shown, not asserted.
- [ ] If user-visible: screenshots attached directly to the PR.
