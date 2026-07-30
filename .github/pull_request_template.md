## Description
Brief description of what this PR does.

## Related Issue
Fixes #(issue number)

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
# Show how to use any new features or fixes
from connectonion import Agent

# Example code
```

## Checklist
- [ ] My code follows the project's code style
- [ ] I have read every line of this diff and can defend each change
- [ ] I have commented my code, particularly in hard-to-understand areas
- [ ] I have made corresponding changes to the documentation
- [ ] My changes generate no new warnings
- [ ] Any dependent changes have been merged and published

## Screenshots (if applicable)
Add screenshots to help explain your changes.

## Additional Notes
Any additional information that reviewers should know.
