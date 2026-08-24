## Description
Brief description of what this PR does.

## Related Issue
Fixes #(issue number)

## Labels and target release (required)

- **Suggested labels:** [bug, feature, documentation, tests, design, browser, platform]
- **Proposed target version:** [e.g. next patch, 1.8.0, 2.x, or TBD]
- **Estimated release window:** [e.g. next alpha, next stable, future roadmap, or unknown]
- **Milestone:** [maintainer assigns the confirmed release milestone]
- **Why this release:** Explain urgency, dependencies, compatibility, and rollback risk.
- **Forward-port tracking issue (stable patches only):** [link an open `forward-port-required` issue, for example #123; use N/A for non-patch work]

> The author's target is an estimate. Maintainers confirm the release by applying labels and assigning a milestone.

## How this was written

- [ ] I wrote this myself
- [ ] AI-assisted — I reviewed every line and can explain why each change is there
- [ ] Mostly AI-generated

**Which model?** e.g. Claude Opus 4.5, GPT-5, Gemini 3 Pro — and the tool, e.g. Claude Code, Cursor, Codex.

> 

Model capability directly affects code quality, and knowing which one wrote this tells a reviewer where to look. It is not used to reject anything — an AI-assisted PR is as welcome as any other. It calibrates review.

**If AI was involved at all, answer these in prose. "I'm not sure" is a fine answer — pretending to be sure is not.**

- Which part of this are you least confident about?
- What did you *not* verify — which paths did you never actually run?
- If this is wrong, what breaks first?

> 

A PR that says *"I didn't test the Windows path and I'm unsure the retry logic is right"* gets reviewed. A PR that claims everything is correct and complete, when nobody read it, gets closed.

## Type of Change
- [ ] Bug fix (non-breaking change which fixes an issue)
- [ ] New feature (non-breaking change which adds functionality)
- [ ] Breaking change (fix or feature that would cause existing functionality to not work as expected)
- [ ] Documentation update

## Dev Blog (required)

**Every PR ships a dev-blog post in the same diff** — a file added or updated under `docs/blog/`. This is enforced by CI (`blog-gate`).

The posts sync to the docs site, so writing it here is what keeps the site current without anyone asking.

What the post is: a short Design Journal piece telling the **story** of this change — the problem as someone actually hit it, a turn or complication, what the fix teaches, what was measured. Written for a reader who could stop reading at any point.
What it is not: a changelog entry, a list of commits, or marketing copy.

The gate reviews the writing, not just the file: a post without a narrative arc — a changelog wearing prose — fails the check, with the model's one concrete fix in the error. A merged PR means its story was worth reading.

Blog file in this PR:

> docs/blog/YYYY-MM-DD-<slug>.md

Genuinely trivial change (typo, lockfile, CI plumbing)? A maintainer can apply the `no-blog` label to waive the gate — that is the maintainer's call, not the author's.

## Changes Made
- List the main changes
- Be specific about what was modified
- Include any dependencies that were added

## Testing

Paste the actual command and its real output. The output is the evidence — a ticked box is not.

```
$ pytest tests/ -m "not real_api and not network"
```

- [ ] I have added tests for new functionality

## Scope

Which files does this touch, and why does each one need to change?

> 

Keep a PR to one concern. A change that spans several subsystems at once is hard to review and hard to own — and that is the most common reason we close an otherwise-correct PR. Not because the code is wrong, but because nobody can say what the resulting design is.

## Example Usage
```python
from connectonion import Agent

# Show how to use any new features or fixes
```

## Checklist
- [ ] I proposed at least one label and a target version above
- [ ] My code follows the project's code style
- [ ] I have read every line of this diff and can defend each change
- [ ] I have commented my code, particularly in hard-to-understand areas
- [ ] I have made corresponding changes to the documentation
- [ ] This PR ships its dev-blog post under docs/blog/ (or a maintainer applied `no-blog`)
- [ ] My changes generate no new warnings
- [ ] Any dependent changes have been merged and published
- [ ] If this targets a stable patch, its separate `forward-port-required`
      tracker names every active higher line, at minimum the current preview,
      and will remain open until all applicable forward-port PRs merge and pass CI
- [ ] Every piece of evidence the linked issue's **AI implementation contract**
      requires is attached or linked here (tests, journeys, screenshots,
      exact commands) — see docs/ai-implementation-contract.md

## Screenshots (if applicable)
Add screenshots to help explain your changes.

## Additional Notes
Any additional information that reviewers should know.
