---
name: Bug report
about: Create a report to help us improve
title: '[BUG] '
labels: 'bug'
assignees: ''

---

**Describe the bug**
A clear and concise description of what the bug is.

**To Reproduce**
Steps to reproduce the behavior:
1. Install ConnectOnion version '...'
2. Run code '....'
3. See error

**Expected behavior**
A clear and concise description of what you expected to happen.

**Code Example**
```python
# Minimal code example that reproduces the issue
from connectonion import Agent

# Your code here
```

**Error Output**
```
# Paste the full error traceback here
```

**Environment (please complete the following information):**
 - OS: [e.g. macOS, Ubuntu, Windows]
 - Python Version: [e.g. 3.10, 3.11, 3.12]
 - ConnectOnion Version: [e.g. 0.0.5]
 - OpenAI API Key configured: [yes/no]

**Additional context**
Add any other context about the problem here.
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
