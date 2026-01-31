---
name: review-pr
description: Review GitHub pull requests. Use when user says "review PR", "review pull request", or "/review-pr".
---

# PR Review Skill

Review a GitHub pull request for code quality, correctness, and best practices.

## Instructions

1. **Get PR information**:
   - If no PR number given: `gh pr list` to show open PRs
   - With PR number: `gh pr view <number>` for details
   - Get diff: `gh pr diff <number>`

2. **Analyze the changes**:
   - What does this PR do?
   - Does the code follow project conventions?
   - Are there any bugs or issues?
   - Is the code well-tested?
   - Are there security concerns?

3. **Provide structured review**:
   - Overview of what the PR does
   - Code quality analysis
   - Specific suggestions with line references
   - Potential issues or risks
   - Whether to approve, request changes, or comment

## Review Checklist

- [ ] Code correctness
- [ ] Following project conventions
- [ ] Error handling
- [ ] Performance implications
- [ ] Test coverage
- [ ] Security considerations
- [ ] Documentation updates needed

## Output Format

```markdown
## PR Review: #<number> - <title>

### Summary
<One paragraph about what this PR does>

### What's Good
- Point 1
- Point 2

### Suggestions
1. **File:line** - Description of suggestion
2. **File:line** - Description of suggestion

### Concerns
- Any potential issues

### Recommendation
- [ ] Approve
- [ ] Request Changes
- [ ] Comment only
```

## Example

```bash
# Get PR details
gh pr view 123

# Get the diff
gh pr diff 123

# Then analyze and provide review
```
