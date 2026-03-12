# Skills

Skills are reusable, pre-packaged workflows with automatic permission management. Define once, invoke with `/skill-name`, and let agents execute complex tasks with proper tool permissions.

## Quick Start

```python
from connectonion import Agent
from connectonion.useful_tools import FileTools
from connectonion.useful_plugins import skills

file_tools = FileTools()
agent = Agent("assistant", tools=[file_tools], plugins=[skills])

# User types: /commit
# → Skills plugin detects command
# → Loads .co/skills/commit/SKILL.md content
# → Sets permission scope for git commands
# → Agent executes with auto-approved tools
```

## What is a Skill?

A skill is a markdown file with:
1. **YAML frontmatter** - Metadata (name, description, allowed tools)
2. **Instructions** - What the agent should do

Skills combine **instant invocation** (via plugins) with **scoped permissions** (temporary tool auto-approval).

### Example: Commit Skill

```yaml
---
name: commit
description: Create git commits with good messages
tools:
  - Bash(git status)
  - Bash(git diff *)
  - Bash(git commit *)
  - Bash(git log *)
  - Bash(git add *)
  - FileTools.read_file
  - FileTools.glob
---

# Git Commit Skill

Create a well-formatted git commit for staged changes.

## Instructions

1. **Gather information** (run in parallel):
   - `git status` - See what's staged and unstaged
   - `git diff --staged` - See exactly what will be committed
   - `git log --oneline -5` - See recent commit message style

2. **Analyze changes**:
   - What was changed? (files, functions, features)
   - Why was it changed? (bug fix, new feature, refactor)
   - Follow the repository's commit message style

3. **Draft commit message**:
   - First line: concise summary under 50 chars
   - Focus on "why" not "what"
   - Match existing commit style

4. **Execute commit**:
   - Stage relevant files if needed: `git add <files>`
   - Commit with message

## Safety Rules

- Do NOT commit .env or credential files
- Do NOT use `--amend` unless explicitly asked
- Do NOT push unless explicitly asked
```

## How It Works

### 1. Discovery & Loading

Skills are discovered from three locations (priority order):

```
1. .co/skills/skill-name/SKILL.md    # Project-level (highest priority)
2. ~/.co/skills/skill-name/SKILL.md  # User-level
3. builtin/skill-name/SKILL.md       # Built-in (lowest priority)
```

Skills are loaded once at agent creation, descriptions injected into system prompt.

### 2. Invocation

**Two ways to invoke:**

#### A. `/command` (Instant - Recommended)

```python
# User types: /commit
# Skills plugin intercepts in @after_user_input
# → Loads full SKILL.md content
# → Takes snapshot of current permissions (preserves user approvals)
# → Grants skill permissions to unified permissions dict
# → Replaces user message with skill instructions
# → Agent proceeds with permissions
# → Turn ends, snapshot restored
```

**No LLM overhead** - instant execution before LLM sees the message.

#### B. `skill()` tool (LLM decides)

```python
# Agent can choose to invoke skill
# → LLM calls skill(name="commit")
# → Tool loads SKILL.md, grants permissions with snapshot
# → Continues execution with permissions
```

**LLM overhead** - requires decision-making step.

### 3. Unified Permissions with Snapshot/Restore

When a skill is invoked, permissions are granted using unified permission structure with snapshot/restore:

```python
# Turn 5: Skill invoked
# Step 1: Snapshot current permissions
snapshot = deepcopy(session['permissions'])  # Preserves user approvals

# Step 2: Grant skill permissions
session['permissions'] = {
    # User approvals preserved from snapshot
    "write": {
        "allowed": True,
        "source": "user",
        "reason": "approved for session",
        "expires": {"type": "session_end"}
    },
    # Skill permissions added (unified format with 'when' field)
    "bash": {
        "allowed": True,
        "source": "skill",
        "reason": "commit skill (turn 5)",
        "when": {"command": "git *"},  # Granular - only git commands
        "expires": {"type": "turn_end"}
    },
    "read_file": {
        "allowed": True,
        "source": "skill",
        "reason": "commit skill (turn 5)",
        "expires": {"type": "turn_end"}
    }
}

# Step 3: Turn ends (@on_complete)
session['permissions'] = snapshot  # Restore original permissions
```

**Lifecycle:**
- **Set**: Snapshot taken, skill permissions granted
- **Active**: During turn only
- **Restored**: At turn end via `@on_complete` event

**Security:** Snapshot/restore ensures:
- ✅ User approvals never overwritten by skills
- ✅ Skill permissions cleared after turn
- ✅ Predictable state before/after skill

### 4. Approval Flow

The `tool_approval` plugin checks permissions in this order:

```
1. Check skill's allowed_tools → Auto-approve if match
2. Check SAFE_TOOLS (read, glob, grep) → Auto-approve
3. Check session memory (previous approvals) → Auto-approve
4. Check DANGEROUS_TOOLS → Ask user
```

**Pattern matching** for flexible permissions:

```yaml
tools:
  - Bash(git status)     # Exact match only
  - Bash(git diff *)     # Wildcard: git diff --staged, git diff HEAD
  - Bash(git *)          # All git commands
  - bash                 # All bash commands (not recommended)
  - read_file            # Tool name only
```

## SKILL.md Format

### Frontmatter (Required)

```yaml
---
name: skill-name          # Required: CLI invocation name (/skill-name)
description: Short desc   # Required: Shown in system prompt
tools:                    # Optional: Auto-approved tools during execution
  - tool_name
  - Bash(command pattern)
---
```

### Instructions (Required)

Markdown content after frontmatter - instructions for the agent.

**Best practices:**
- Clear step-by-step instructions
- Include examples where helpful
- Document safety rules
- Show expected command formats

## Creating Skills

### 1. Project-Level Skill (Specific to one project)

```bash
mkdir -p .co/skills/deploy
cat > .co/skills/deploy/SKILL.md <<'EOF'
---
name: deploy
description: Deploy package to PyPI
tools:
  - Bash(python -m build)
  - Bash(python -m twine *)
  - Bash(git tag *)
  - Bash(git push *)
  - read_file
  - edit
---

# Deploy Skill

Deploy the package to PyPI.

## Steps

1. Run tests: `pytest`
2. Update version in setup.py
3. Build package: `python -m build`
4. Upload to PyPI: `python -m twine upload dist/*`
5. Create git tag: `git tag v0.4.2`
6. Push tag: `git push origin v0.4.2`
EOF
```

### 2. User-Level Skill (Reusable across projects)

```bash
mkdir -p ~/.co/skills/review
cat > ~/.co/skills/review/SKILL.md <<'EOF'
---
name: review
description: Code review workflow
tools:
  - Bash(git diff *)
  - Bash(git log *)
  - read_file
  - glob
  - grep
---

# Code Review Skill

Review recent changes and provide feedback.

## Steps

1. See what changed: `git diff main...HEAD`
2. Read modified files
3. Check for:
   - Code quality issues
   - Potential bugs
   - Missing tests
   - Type hints
4. Provide feedback
EOF
```

### 3. Built-in Skill (Shipped with ConnectOnion)

Built-in skills are in `connectonion/cli/co_ai/skills/builtin/`.

Users can override by creating same-named skill in project or user level.

## Permission Patterns

### Exact Match

```yaml
tools:
  - Bash(git status)  # Only "git status" allowed
```

Allows: `git status`
Blocks: `git status -v`, `git diff`

### Wildcard Match

```yaml
tools:
  - Bash(git diff *)  # git diff with any args
```

Allows: `git diff`, `git diff --staged`, `git diff HEAD~1`
Blocks: `git status`, `git commit`

### Command Match

```yaml
tools:
  - Bash(git *)  # All git commands
```

Allows: `git status`, `git diff`, `git commit -m "msg"`
Blocks: `rm -rf`, `pytest`

### Tool Match

```yaml
tools:
  - bash  # All bash commands (dangerous!)
```

Allows: Any bash command
Use with caution - defeats the purpose of scoped permissions.

### Tool Name Only

```yaml
tools:
  - read_file  # Tool name without arguments
  - glob
  - grep
```

Allows: All calls to these tools with any arguments.

## Architecture

### Plugin Implementation

```python
from connectonion import after_user_input, on_complete
from copy import deepcopy

@after_user_input
def _handle_skill_invocation(agent):
    """Detect /command and load skill with snapshot/restore."""
    user_msg = agent.current_session['messages'][-1]['content']

    if not user_msg.startswith('/'):
        return  # Not a skill invocation

    skill_name = user_msg[1:].split()[0]
    skill_info = get_skill(skill_name)

    if not skill_info:
        return  # Skill not found

    # Load full SKILL.md content
    content = skill_info.load_content()
    frontmatter = parse_skill_frontmatter(content)

    # Snapshot current permissions (preserves user approvals)
    current_perms = agent.current_session.get('permissions', {})
    agent.current_session['_permission_snapshot'] = deepcopy(current_perms)

    # Grant skill permissions to unified permissions dict
    if 'permissions' not in agent.current_session:
        agent.current_session['permissions'] = {}

    turn = agent.current_session.get('turn', 0)
    for pattern in frontmatter.get('tools', []):
        agent.current_session['permissions'][pattern] = {
            'allowed': True,
            'source': 'skill',
            'reason': f'{skill_name} skill (turn {turn})',
            'expires': {'type': 'turn_end'}
        }

    # Replace user message with skill instructions
    instructions = content.split('---', 2)[2].strip()
    agent.current_session['messages'][-1]['content'] = instructions

@on_complete
def _cleanup_scope(agent):
    """Restore permissions snapshot after turn completes."""
    if '_permission_snapshot' in agent.current_session:
        agent.current_session['permissions'] = agent.current_session.pop('_permission_snapshot')

skills = [_handle_skill_invocation, _cleanup_scope]
```

### Tool Approval Integration

The `tool_approval` plugin checks unified `permissions` dict:

```python
@before_each_tool
def check_approval(agent):
    """Check if tool needs approval using unified permissions."""

    tool_name = pending['name']
    tool_args = pending['arguments']

    # Check unified permissions dict
    permissions = agent.current_session.get('permissions', {})

    # Ensure safe tools are in permissions
    if tool_name in SAFE_TOOLS:
        if tool_name not in permissions:
            permissions[tool_name] = {
                'allowed': True,
                'source': 'safe',
                'reason': 'read-only operation',
                'expires': {'type': 'never'}
            }

    # Check each permission with pattern matching
    if permissions:
        for pattern, perm in permissions.items():
            if not perm.get('allowed'):
                continue

            if matches_permission_pattern(tool_name, tool_args, [pattern]):
                reason = perm.get('reason', 'unknown')
                log(f"⚡ {tool_name} ({reason})")
                return  # Auto-approve

    # Ask user for dangerous tools
    if tool_name in DANGEROUS_TOOLS:
        response = agent.io.send({'type': 'approval_needed', ...})
        # If approved for session, add to permissions dict
```

### Pattern Matching

```python
def _matches_pattern(tool_name, tool_args, allowed_patterns):
    """Check if tool call matches allowed patterns."""
    for pattern in allowed_patterns:
        # Tool name only: "read_file"
        if pattern == tool_name:
            return True

        # Bash pattern: "Bash(git status)"
        if pattern.startswith('Bash(') and tool_name == 'bash':
            cmd_pattern = pattern[5:-1]  # Extract "git status"
            actual_cmd = tool_args.get('command', '')

            # Exact match
            if cmd_pattern == actual_cmd:
                return True

            # Wildcard match: "git diff *"
            if cmd_pattern.endswith(' *'):
                prefix = cmd_pattern[:-2]
                if actual_cmd.startswith(prefix):
                    return True

    return False
```

## Session State Structure

```python
agent.current_session = {
    'session_id': 'abc-123',
    'turn': 5,
    'iteration': 2,
    'messages': [...],
    'trace': [...],

    # Unified permissions (single source of truth)
    'permissions': {
        # Safe tools (auto-granted)
        'read_file': {
            'allowed': True,
            'source': 'safe',
            'reason': 'read-only operation',
            'expires': {'type': 'never'}
        },
        # Skill permissions (turn-scoped)
        'Bash(git status)': {
            'allowed': True,
            'source': 'skill',
            'reason': 'commit skill (turn 5)',
            'expires': {'type': 'turn_end'}
        },
        'Bash(git diff *)': {
            'allowed': True,
            'source': 'skill',
            'reason': 'commit skill (turn 5)',
            'expires': {'type': 'turn_end'}
        },
        # User approvals (session-scoped)
        'write': {
            'allowed': True,
            'source': 'user',
            'reason': 'approved for session',
            'expires': {'type': 'session_end'}
        }
    },

    # Permission snapshot (for restore after skill completes)
    '_permission_snapshot': {
        'read_file': {...},
        'write': {...}
        # Skill permissions NOT in snapshot
    }
}
```

## Use Cases

### 1. Commit Workflow

```yaml
---
name: commit
description: Create git commits
tools:
  - Bash(git *)
  - read_file
  - glob
---
Create a git commit with a good message.
```

User types: `/commit`
→ Agent runs git commands without approval prompts
→ Permission scope cleared after commit

### 2. Test & Release Workflow

```yaml
---
name: release
description: Run tests and publish to PyPI
tools:
  - Bash(pytest *)
  - Bash(python -m build)
  - Bash(python -m twine *)
  - Bash(git tag *)
  - Bash(git push *)
  - read_file
  - edit
---
Run tests, build package, and publish to PyPI.
```

User types: `/release`
→ Testing and publishing commands auto-approved
→ Other dangerous commands still require approval

### 3. Code Review

```yaml
---
name: review
description: Review code changes
tools:
  - Bash(git diff *)
  - Bash(git log *)
  - read_file
  - glob
  - grep
---
Review recent changes and provide feedback.
```

User types: `/review`
→ Read-only git commands auto-approved
→ No dangerous operations possible

## Best Practices

### Security

1. **Minimal permissions** - Only list tools the skill truly needs
2. **Specific patterns** - Use `Bash(git status)` not `Bash(git *)`
3. **No wildcards for dangerous commands** - Avoid `Bash(*)`
4. **Regular review** - Audit skill permissions periodically

### Skill Design

1. **Clear instructions** - Step-by-step, no ambiguity
2. **Include examples** - Show expected command formats
3. **Document safety rules** - What NOT to do
4. **Single responsibility** - One skill, one task

### Organization

1. **Project skills** - Deployment, project-specific workflows
2. **User skills** - Personal workflows, code review, etc.
3. **Built-in skills** - Universal workflows (commit, test, etc.)

## Skill + Tool Invocation

Skills can also be invoked by the LLM via the `skill()` tool:

```python
# Agent autonomously decides to use a skill
agent.tools.skill(name="commit")
# → Sets permission scope
# → Returns skill instructions
# → Agent follows instructions with scoped permissions
```

This allows the agent to discover and use skills without explicit `/command` invocation.

## Troubleshooting

### Skill not found

```bash
# Check skill exists
ls .co/skills/skill-name/SKILL.md
ls ~/.co/skills/skill-name/SKILL.md
```

### Permission denied despite skill scope

Check pattern matching - ensure tool call matches pattern:

```yaml
# ❌ WRONG: Pattern too specific
tools:
  - Bash(git diff)  # Blocks "git diff --staged"

# ✅ CORRECT: Use wildcard
tools:
  - Bash(git diff *)  # Allows any git diff variant
```

### Scope not clearing

Permission scope auto-clears at turn end. If it persists:

1. Check `@on_complete` handler is registered
2. Verify turn number increments correctly
3. Manually clear: `agent.current_session.pop('permission_scope', None)`

## Related

- [Permissions](permissions.md) - Complete permission system overview
- [Plugins](plugins.md) - Plugin system overview
- [Events](events.md) - Available event hooks
- [Tool Approval](../useful_plugins/tool_approval.md) - Web-based approval plugin
- [Tools](tools.md) - Tool system overview
