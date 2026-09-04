---
name: Feature request
about: Suggest an idea for ConnectOnion
title: '[FEATURE] '
labels: 'enhancement'
assignees: ''

---

## Problem
What user problem does this solve? Describe the current limitation and who encounters it.

## Proposed solution
Describe the behavior or API you would like.

## Release planning
- **Suggested target version:** [e.g. 1.8.0, 2.x, future roadmap, or TBD]
- **Estimated release window:** [e.g. next alpha, next stable, future roadmap, or unknown]
- **Why this version:** Explain dependencies, urgency, and compatibility impact.

> The reporter's target is an estimate. Maintainers confirm the release by assigning a milestone.

## Example usage
```python
from connectonion import Agent

# Show how the proposed feature would work
agent = Agent("assistant")
```

## Alternatives considered
Describe any alternative solutions or workarounds.

## Implementation help
- [ ] I can submit a PR
- [ ] I can help with guidance
- [ ] I can test the implementation
- [ ] I am only reporting the need

## Additional context
Add any other context, screenshots, or examples.

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
- [ ] If this is a stable patch, open a separate `forward-port-required` issue
      naming every active higher line before the patch PR merges.
- [ ] After a stable patch is verified, forward-port every applicable fix,
      regression test, migration, documentation change, and operational
      contract into every active higher line; preserve newer OIP authority and
      resolve conflicts explicitly instead of copying version metadata.
- [ ] Keep that tracker open until every forward-port PR merges and passes CI.
      No newer preview, RC, or next-minor Stable publishes first.
- [ ] Link rollback instructions, immutable versions/hashes, PRs, screenshots, and
      public release.
