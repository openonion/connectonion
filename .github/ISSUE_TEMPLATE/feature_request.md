---
name: Feature request
about: Suggest an idea for ConnectOnion
title: '[FEATURE] '
labels: 'enhancement'
assignees: ''

---

**Is your feature request related to a problem? Please describe.**
A clear and concise description of what the problem is. Ex. I'm always frustrated when [...]

**Describe the solution you'd like**
A clear and concise description of what you want to happen.

**Example Usage**
Show how the feature would be used:
```python
from connectonion import Agent

# Example of how the feature would work
agent = Agent("assistant")
# Your proposed API usage
```

**Describe alternatives you've considered**
A clear and concise description of any alternative solutions or features you've considered.

**Additional context**
Add any other context, screenshots, or examples about the feature request here.

**Would you be willing to help implement this feature?**
- [ ] Yes, I can submit a PR
- [ ] Yes, but I would need guidance
- [ ] No, but I can help test it
## AI implementation contract

<!-- Fill this in so an AI session can execute without the owner repeating
     the operating contract every round. Full guidance, repository defaults,
     and guardrails: docs/ai-implementation-contract.md -->

### Scope and release line
- Target: [ ] stable patch [ ] preview [ ] main-only [ ] docs/process only
- Exact base/tag:
- Owning repositories:
- Related issues/design decisions:
- Explicitly out of scope:
- Release action authorized by this issue:
  [ ] test only
  [ ] prepare Draft release PR
  [ ] publish approved Preview
  [ ] publish stable
  [ ] no publication

### Plan before code
- Inspect the current implementation, tests, AGENTS/CLAUDE guidance, protocol docs,
  related PRs/issues, and released package behavior.
- Write the implementation/compatibility/test plan before editing.
- Identify security authority, migration, rollback, and old/new version boundaries.
- Do not merge a preview `main` wholesale into a stable branch.

### Required verification
- Unit/component/contract tests:
- Cross-repository fixtures:
- Real browser journey:
- Required desktop/mobile widths:
- Required failure/reconnect/approval states:
- Complex acceptance task:
- Commands and exact output to record:

### UI and interaction review
- [ ] Capture the current baseline before implementation.
- [ ] Hide raw code/terminal detail behind progressive disclosure by default.
- [ ] Run an expert UI/interaction audit after each UI implementation round.
- [ ] Record the ten highest-impact findings and the disposition of each.
- [ ] Re-run the journey after fixes until no release-blocking finding remains.

### Screenshot evidence
- [ ] Attach Before / After screenshots directly to the PR.
- [ ] Attach desktop and narrow/mobile screenshots.
- [ ] Include approval, error/reconnect, running, and completed states when applicable.
- [ ] Link the complete browser artifact/trace.
- [ ] Select permanent release screenshots; do not rely only on expiring CI artifacts.

### Documentation and code knowledge
- [ ] Update user documentation and exact release/version guidance.
- [ ] Update protocol/design decisions and compatibility matrix when a boundary changes.
- [ ] Add concise "why" comments around non-obvious invariants.
- [ ] Boundary files link to their Core writer, React normalizer, O Chat renderer,
      contract fixture, and design decision.
- [ ] Do not add boilerplate headers to unrelated files.

### Release and forward integration
- [ ] Test the reviewed package/artifact, not only a source checkout.
- [ ] Publish only through the protected GitHub Preview/Release workflow explicitly
      authorized above.
- [ ] Re-test the public artifact and deployed Preview.
- [ ] After a stable release is verified, forward-merge that stable line into
      `main`; preserve newer OIP authority and resolve conflicts explicitly.
- [ ] Link rollback instructions, immutable versions/hashes, PRs, screenshots, and
      public release.
