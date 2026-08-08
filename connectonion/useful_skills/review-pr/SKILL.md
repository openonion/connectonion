---
name: review-pr
description: Review GitHub pull requests. Use when user says "review PR", "review pull request", or "/review-pr".
---

# PR Review Skill

Review a GitHub pull request for code quality, correctness, and best practices.

## Instructions

1. **Get PR information**:
   - If no PR number is given, list open PRs.
   - With a PR number, read its metadata, checks, discussion, and complete diff.

2. **Analyze the changes**:
   - What does the PR do?
   - Does the code follow project conventions?
   - Are there correctness, error-handling, compatibility, or security bugs?
   - Do tests cover the important failure modes?

3. **Provide an evidence-based review**:
   - Put concrete findings first, ordered by severity.
   - Include file and line references.
   - Distinguish blockers from optional suggestions.
   - Approve only after tests and CI support the conclusion.

## Review Checklist

- [ ] Code correctness
- [ ] Project conventions
- [ ] Error handling
- [ ] Compatibility and performance
- [ ] Test coverage
- [ ] Security considerations
- [ ] Documentation impact

Reading or submitting a GitHub review must use the agent's normal approval and
authentication policy; this skill grants no shell or network permissions.
