# Skills Plugin

Pre-packaged workflows with automatic permission management. Invoke with `/skill-name` for instant execution.

## Quick Start

```python
from connectonion import Agent
from connectonion.useful_tools import FileTools
from connectonion.useful_plugins import skills, tool_approval

file_tools = FileTools()  # Read/edit files with safety tracking
agent = Agent(
    "assistant",
    tools=[file_tools],
    plugins=[skills, tool_approval]  # skills must come before tool_approval
)

# User types: /commit
# → Skills plugin loads .co/skills/commit/SKILL.md
# → Sets temporary permission scope for git commands
# → Agent executes with auto-approved tools
# → Scope clears after turn completes
```

## What Skills Do

1. **Instant invocation** - `/command` detected in `@after_user_input`, no LLM overhead
2. **Scoped permissions** - Temporary tool auto-approval for skill duration
3. **Security** - Permissions auto-clear after turn completes

## Example Skill

```yaml
---
name: commit
description: Create git commits with good messages
tools:
  - Bash(git status)
  - Bash(git diff *)
  - Bash(git commit *)
  - Bash(git add *)
  - FileTools.read_file
  - FileTools.glob
---

Create a well-formatted git commit for staged changes.

1. Check status: `git status`
2. Review changes: `git diff --staged`
3. Create commit with good message
```

User types: `/commit` → git commands auto-approved → commit created → permissions cleared.

## Creating Skills

### Project-level (`.co/skills/`)

```bash
mkdir -p .co/skills/deploy
cat > .co/skills/deploy/SKILL.md <<'EOF'
---
name: deploy
description: Prepare a reviewed, tag-driven PyPI release
tools:
  - Bash(pytest *)
  - Bash(python -m build)
  - Bash(python -m twine check *)
  - Bash(gh pr *)
  - Bash(gh run *)
  - Bash(git tag *)
  - Bash(git push *)
---

Run tests, validate the exact package, merge the release PR, tag
`<reviewed-merge-commit>`, and wait for `.github/workflows/release.yml` to
publish through PyPI Trusted Publishing.
EOF
```

### User-level (`~/.co/skills/`)

```bash
mkdir -p ~/.co/skills/review
cat > ~/.co/skills/review/SKILL.md <<'EOF'
---
name: review
description: Code review workflow
tools:
  - Bash(git diff *)
  - Bash(git log *)
  - FileTools.read_file
  - FileTools.glob
  - FileTools.grep
---

Review recent code changes and provide feedback.
EOF
```

## Permission Patterns

```yaml
tools:
  - Bash(git status)         # Exact: only "git status"
  - Bash(git diff *)         # Wildcard: any git diff command
  - Bash(git *)              # All git commands
  - FileTools.read_file      # FileTools method (any arguments)
  - FileTools.edit           # FileTools method
  - FileTools.glob           # FileTools method
```

## Architecture

Skills plugin uses two event handlers:

```python
@after_user_input
def _handle_skill_invocation(agent):
    """Detect /command, load skill, set permission_scope"""
    # Intercepts before LLM sees message
    # Loads SKILL.md content
    # Sets permission_scope in session with turn number
    # Replaces user message with skill instructions

@on_complete
def _cleanup_scope(agent):
    """Clear permission_scope after turn completes"""
    # Removes permissions when turn ends
    # Ensures security - permissions don't persist
```

The `tool_approval` plugin checks `permission_scope` first:

```
1. Skill's allowed_tools → Auto-approve if match
2. Template/config permissions → Auto-approve if match
3. Session memory and explicit mode permissions → Auto-approve if match
4. Ask for every remaining live-IO tool
```

## Security Model

**One-turn permissions** - Scope is tied to turn number:

```
Turn 5: User invokes /commit
  → permission_scope set with turn=5
  → git commands auto-approved during turn 5
  → Agent creates commit, turn ends
  → permission_scope cleared

Turn 6: User types "refactor the code"
  → git permissions NO LONGER active
  → Dangerous commands require approval again
```

This prevents accidental permission escalation across turns.

## Full Documentation

See [Skills](skills.md) for complete documentation:
- SKILL.md format specification
- Pattern matching details
- Session state structure
- Use cases and examples
- Best practices
- Troubleshooting

## Related

- [Permissions](../features/permissions.md) - Complete permission system overview
- [Tool Approval](tool_approval.md) - Web-based approval plugin that skills integrate with
- [Plugins](../concepts/plugins.md) - Plugin system overview
- [Events](../concepts/events.md) - Event hooks used by skills
