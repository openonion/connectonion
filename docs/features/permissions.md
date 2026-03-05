# Permissions

ConnectOnion provides multiple permission mechanisms to balance safety and automation. This guide explains how they work together.

## Permission Layers

```
┌─────────────────────────────────────────────────────────────┐
│ 1. SAFE_TOOLS - Always auto-approved                       │
│    FileTools.read_file, FileTools.glob, FileTools.grep     │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│ 2. Skills - Temporary scoped permissions (one turn)         │
│    /commit → auto-approve git commands for this turn only  │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│ 3. Plan Mode - Auto-edit in planning phase                 │
│    Edit tool auto-approved when agent.is_planning=True     │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│ 4. Session Memory - Remember user decisions                │
│    User approved bash once → auto-approve for session      │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│ 5. Tool Approval - Ask user for dangerous operations       │
│    bash, edit, write → require explicit user approval      │
└─────────────────────────────────────────────────────────────┘
```

## Quick Start

```python
from connectonion import Agent
from connectonion.useful_tools import FileTools
from connectonion.useful_plugins import skills, tool_approval

file_tools = FileTools()
agent = Agent(
    "assistant",
    tools=[file_tools],
    plugins=[skills, tool_approval]
)

# Safe tools - auto-approved
agent.input("Read the README")
# → read_file auto-approved ✓

# Skills - scoped permissions
# User types: /commit
# → git commands auto-approved for this turn only ✓
# → Turn ends, permissions cleared ✓

# Plan mode - auto-edit during planning
agent.is_planning = True
agent.input("Plan how to add a feature")
# → edit auto-approved during planning ✓

agent.is_planning = False
# → edit requires approval again ✓

# Session memory - remember decisions
agent.input("Run tests")
# → bash approval needed (first time)
# → User approves for "session"
# → Future bash calls auto-approved ✓

# Dangerous operations - always ask
agent.input("Delete all files")
# → User approval required (destructive operation)
```

## 1. SAFE_TOOLS - Always Auto-Approved

Read-only operations that can't harm the system.

```python
SAFE_TOOLS = [
    'FileTools.read_file',
    'FileTools.glob',
    'FileTools.grep',
    'ls',
    'list_directory',
    'tree'
]
```

**No approval needed** - these tools are always safe to execute.

### Example

```python
agent.input("Find all Python files and read main.py")
# → FileTools.glob("**/*.py") - auto-approved ✓
# → FileTools.read_file("main.py") - auto-approved ✓
```

## 2. Skills - Temporary Scoped Permissions with Snapshot/Restore

Pre-packaged workflows with **one-turn** automatic tool approval that preserves user approvals.

### How It Works - Unified Permissions

```python
# Turn 3: User approved bash:pytest for session
session['permissions'] = {
    "bash:pytest": {
        "allowed": True,
        "source": "user",
        "reason": "approved for session",
        "expires": {"type": "session_end"}
    }
}

# Turn 5: User types /commit
# Step 1: Take snapshot of current permissions
snapshot = deepcopy(session['permissions'])  # Preserves bash:pytest

# Step 2: Grant skill permissions
session['permissions'] = {
    "bash:pytest": {  # Preserved from snapshot
        "allowed": True,
        "source": "user",
        "reason": "approved for session",
        "expires": {"type": "session_end"}
    },
    "Bash(git status)": {  # Added by skill
        "allowed": True,
        "source": "skill",
        "reason": "commit skill (turn 5)",
        "expires": {"type": "turn_end"}
    },
    "Bash(git diff *)": {  # Added by skill
        "allowed": True,
        "source": "skill",
        "reason": "commit skill (turn 5)",
        "expires": {"type": "turn_end"}
    }
}

# During turn 5:
# → git status - auto-approved (skill permission) ✓
# → git diff --staged - auto-approved (skill permission) ✓
# → git commit -m "msg" - auto-approved (skill permission) ✓
# → bash:pytest - auto-approved (user permission) ✓
# → rm -rf - BLOCKED (no permission) ✗

# Turn 5 ends (@on_complete)
# Step 3: Restore snapshot
session['permissions'] = snapshot  # User's bash:pytest preserved ✓

# Turn 6: User continues
# → bash:pytest - still works ✓ (user approval preserved)
# → git status - requires approval ✗ (skill permission cleared)
```

### Security Model with Snapshot/Restore

**Snapshot → Grant → Restore** - User approvals are never lost.

```
Turn 3: User approves bash:pytest for session
  └─ permissions['bash:pytest'] = {source: 'user', expires: 'session_end'}

Turn 5: /commit skill
  ├─ Snapshot current permissions (bash:pytest saved)
  ├─ Grant skill permissions (git commands added)
  ├─ Tools execute with both user + skill permissions
  └─ Turn ends → Restore snapshot
      └─ bash:pytest preserved ✓
      └─ git commands cleared ✓

Turn 6: Continue conversation
  ├─ bash:pytest - still works (user approval)
  └─ git commands - require approval (skill cleared)
```

**Benefits:**
- ✅ User approvals never overwritten by skills
- ✅ Skills add temporary permissions, don't replace
- ✅ Clean lifecycle - snapshot/restore is predictable
- ✅ No permission escalation across turns

### Permission Patterns

```yaml
# Exact match
tools:
  - Bash(git status)  # Only "git status"

# Wildcard match
tools:
  - Bash(git diff *)  # Any "git diff ..." command

# Command match
tools:
  - Bash(git *)  # All git commands

# Tool match
tools:
  - read_file  # Tool name (any args)
```

### Example Skill

```yaml
---
name: commit
description: Create git commits
tools:
  - Bash(git status)
  - Bash(git diff *)
  - Bash(git commit *)
  - Bash(git add *)
  - read_file
  - glob
---

Create a well-formatted git commit.

1. Check status: `git status`
2. Review changes: `git diff --staged`
3. Create commit with good message
```

See [Skills](skills.md) for complete documentation.

## 3. Plan Mode - Auto-Edit During Planning

When `agent.is_planning = True`, the `edit` tool is auto-approved.

### Why This Exists

Planning involves iterative code exploration and documentation:

```python
agent.is_planning = True
agent.input("Plan how to add user authentication")

# Agent explores codebase
# → read_file("auth.py") - auto-approved ✓
# → edit("PLAN.md", ...) - auto-approved ✓  (add auth flow diagram)
# → read_file("models.py") - auto-approved ✓
# → edit("PLAN.md", ...) - auto-approved ✓  (add database schema)
# → read_file("routes.py") - auto-approved ✓
# → edit("PLAN.md", ...) - auto-approved ✓  (add route changes)
```

Without auto-edit, user would need to approve every plan update - disruptive to planning flow.

### Implementation

```python
@before_each_tool
def check_approval(agent):
    tool_name = agent.current_session['pending_tool_call']['name']

    # Auto-approve edit during planning
    if tool_name == 'edit' and agent.is_planning:
        return  # Auto-approve

    # ... rest of approval logic
```

### Safety

- **Only during planning** - `is_planning` must be explicitly set
- **Only edit tool** - Other dangerous tools (bash, write) still require approval
- **User controls planning mode** - Agent can't set `is_planning = True` itself

### Example

```python
from connectonion import Agent
from connectonion.useful_plugins import tool_approval

agent = Agent("planner", tools=[read_file, edit, bash], plugins=[tool_approval])

# Planning phase - auto-edit
agent.is_planning = True
agent.input("Create implementation plan for feature X")
# → edit("PLAN.md", ...) auto-approved ✓
# → bash still requires approval ✗

# Implementation phase - require approval
agent.is_planning = False
agent.input("Implement the plan")
# → edit requires approval ✗
# → bash requires approval ✗
```

## 4. Session Memory - Remember User Decisions

When user approves a tool, remember the decision for the session.

### How It Works

```python
# First bash call
agent.input("Run tests")
# → bash approval needed

# User approves with scope: "session"
# ┌─────────────────────────────────────────┐
# │ session['approval'] = {                 │
# │   'approved_tools': {                   │
# │     'bash': 'session'                   │
# │   }                                     │
# │ }                                       │
# └─────────────────────────────────────────┘

# Future bash calls
agent.input("Run linter")
# → bash auto-approved (already approved) ✓

agent.input("Deploy to production")
# → bash auto-approved (already approved) ✓
```

### Approval Scopes

User can choose approval scope:

| Scope | Duration | Use Case |
|-------|----------|----------|
| `once` | Single tool call | Dangerous one-off operations |
| `session` | Entire session | Development workflows |
| `deny` | Permanent (for session) | Block dangerous operations |

### Example Approval UI

```
⚠️  Approval needed for: bash

Command: pytest tests/

┌─────────────────────────────────────┐
│ Approve once                        │
│ Approve for session (recommended)   │
│ Deny                                │
└─────────────────────────────────────┘
```

### Implementation

```python
@before_each_tool
def check_approval(agent):
    tool_name = agent.current_session['pending_tool_call']['name']

    # Check session memory
    approved_tools = agent.current_session.get('approval', {}).get('approved_tools', {})

    if tool_name in approved_tools:
        scope = approved_tools[tool_name]

        if scope == 'session':
            return  # Auto-approve

        if scope == 'deny':
            raise ToolDenied(f"{tool_name} was denied")

    # ... ask user for approval
```

## 5. Tool Approval - Ask User for Dangerous Operations

Web-based approval UI for dangerous tools.

### Dangerous Tools

```python
DANGEROUS_TOOLS = [
    'bash',
    'edit',
    'write',
    'delete_file',
    'execute_code'
]
```

### Approval Flow

```
1. Agent wants to use bash
   ↓
2. Tool approval plugin intercepts
   ↓
3. Send approval request to web UI
   ┌──────────────────────────────────┐
   │ ⚠️ Approval needed: bash         │
   │                                  │
   │ Command: rm -rf /tmp/cache       │
   │                                  │
   │ [Approve once]                   │
   │ [Approve for session]            │
   │ [Deny]                           │
   └──────────────────────────────────┘
4. User decides
   ↓
5. Tool executes (or blocked)
```

### Implementation

```python
@before_each_tool
def check_approval(agent):
    """Check if tool needs approval before execution."""

    tool_name = agent.current_session['pending_tool_call']['name']
    tool_args = agent.current_session['pending_tool_call']['arguments']

    # 1. Check skill permission scope (highest priority)
    scope = agent.current_session.get('permission_scope')
    if scope and scope['turn'] == agent.current_session['turn']:
        if _matches_pattern(tool_name, tool_args, scope['allowed_tools']):
            return  # Auto-approve

    # 2. Check SAFE_TOOLS
    if tool_name in SAFE_TOOLS:
        return  # Auto-approve

    # 3. Check plan mode auto-edit
    if tool_name == 'edit' and agent.is_planning:
        return  # Auto-approve

    # 4. Check session memory
    approved_tools = agent.current_session.get('approval', {}).get('approved_tools', {})
    if tool_name in approved_tools and approved_tools[tool_name] == 'session':
        return  # Auto-approve

    # 5. Check if denied
    if tool_name in approved_tools and approved_tools[tool_name] == 'deny':
        raise ToolDenied(f"{tool_name} was denied")

    # 6. Ask user for dangerous tools
    if tool_name in DANGEROUS_TOOLS:
        response = agent.io.send({
            'type': 'approval_needed',
            'tool_name': tool_name,
            'tool_args': tool_args
        })

        scope = response['scope']  # 'once', 'session', 'deny'

        if scope == 'deny':
            agent.current_session.setdefault('approval', {})['approved_tools'][tool_name] = 'deny'
            raise ToolDenied(f"User denied {tool_name}")

        if scope == 'session':
            agent.current_session.setdefault('approval', {})['approved_tools'][tool_name] = 'session'

        # scope == 'once' → just execute this time

tool_approval = [before_each_tool(check_approval)]
```

See [Tool Approval](../useful_plugins/tool_approval.md) for complete documentation.

## Permission Priority Order

The approval system uses unified permissions - all permissions stored in `session['permissions']`:

```
1. Check unified permissions dict
   ├─ Loop through all permissions
   ├─ Pattern match tool against each permission
   └─ If match found → AUTO-APPROVE ✓
       └─ Log: "⚡ tool_name (reason from permission)"

2. If no match in permissions
   └─ ASK USER (web approval UI)
       └─ If approved for "session" → Add to permissions dict
```

**All permission sources use the same structure:**

```python
session['permissions'] = {
    "read_file": {
        "allowed": True,
        "source": "safe",
        "reason": "read-only operation",
        "expires": {"type": "never"}
    },
    "Bash(git *)": {
        "allowed": True,
        "source": "skill",
        "reason": "commit skill (turn 5)",
        "expires": {"type": "turn_end"}
    },
    "bash:pytest": {
        "allowed": True,
        "source": "user",
        "reason": "approved for session",
        "expires": {"type": "session_end"}
    }
}
```

## Complete Example

```python
from connectonion import Agent
from connectonion.useful_plugins import skills, tool_approval

agent = Agent(
    "dev-assistant",
    tools=[bash, read_file, glob, grep, edit, write],
    plugins=[skills, tool_approval]
)

# ────────────────────────────────────────────────────────
# Scenario 1: Safe tools (always auto-approved)
# ────────────────────────────────────────────────────────
agent.input("Find all tests")
# → glob("**/test_*.py") - SAFE_TOOLS ✓
# → read_file("test_agent.py") - SAFE_TOOLS ✓

# ────────────────────────────────────────────────────────
# Scenario 2: Skills (scoped permissions for one turn)
# ────────────────────────────────────────────────────────
# User types: /commit

# Turn 5:
# → git status - permission_scope ✓
# → git diff - permission_scope ✓
# → git commit - permission_scope ✓

# Turn 6:
# → git commands need approval again

# ────────────────────────────────────────────────────────
# Scenario 3: Plan mode (auto-edit during planning)
# ────────────────────────────────────────────────────────
agent.is_planning = True
agent.input("Plan feature implementation")
# → read_file - SAFE_TOOLS ✓
# → edit("PLAN.md", ...) - plan mode ✓
# → bash - REQUIRES APPROVAL ✗

agent.is_planning = False

# ────────────────────────────────────────────────────────
# Scenario 4: Session memory (remember user decisions)
# ────────────────────────────────────────────────────────
agent.input("Run tests")
# → bash("pytest") - REQUIRES APPROVAL
# → User approves for "session"
# → session['approval']['approved_tools']['bash'] = 'session'

agent.input("Run linter")
# → bash("ruff") - session memory ✓

agent.input("Deploy")
# → bash("./deploy.sh") - session memory ✓

# ────────────────────────────────────────────────────────
# Scenario 5: Dangerous operations (always ask)
# ────────────────────────────────────────────────────────
agent.input("Create new config file")
# → write("config.json", ...) - REQUIRES APPROVAL
# → User approves "once"
# → Executes this time only

agent.input("Create another file")
# → write("data.json", ...) - REQUIRES APPROVAL again
```

## Flow Diagram

```
┌─────────────────────────┐
│ Agent wants to use tool │
└────────────┬────────────┘
             │
             ▼
┌────────────────────────────────┐
│ 1. Skills permission scope?    │
│    (turn-specific)              │
└─────┬──────────────────────┬───┘
  YES │                      │ NO
      ▼                      ▼
   ┌──────┐     ┌────────────────────────┐
   │ ✓ OK │     │ 2. SAFE_TOOLS?         │
   └──────┘     └─────┬──────────────┬───┘
                  YES │              │ NO
                      ▼              ▼
                   ┌──────┐     ┌────────────────────────┐
                   │ ✓ OK │     │ 3. Plan mode + edit?   │
                   └──────┘     └─────┬──────────────┬───┘
                                  YES │              │ NO
                                      ▼              ▼
                                   ┌──────┐     ┌────────────────────────┐
                                   │ ✓ OK │     │ 4. Session memory?     │
                                   └──────┘     └─────┬──────────────┬───┘
                                                  YES │              │ NO
                                                      ▼              ▼
                                               ┌────────────┐   ┌──────────────┐
                                               │ ✓ approved │   │ 5. Ask user  │
                                               │ ✗ denied   │   └──────┬───────┘
                                               └────────────┘          │
                                                                       ▼
                                                            ┌─────────────────────┐
                                                            │ once / session /    │
                                                            │ deny                │
                                                            └──────┬──────────────┘
                                                                   │
                                                        ┌──────────┼──────────┐
                                                        │          │          │
                                                        ▼          ▼          ▼
                                                     ┌────┐   ┌────────┐  ┌──────┐
                                                     │ ✓  │   │ ✓ save │  │ ✗    │
                                                     │once│   │ to     │  │deny  │
                                                     └────┘   │session │  └──────┘
                                                              └────────┘
```

## Best Practices

### 1. Use Skills for Workflows

```python
# ❌ BAD: Manual approval for every git command
agent.input("Create a commit")
# → git status - approval needed
# → git diff - approval needed
# → git commit - approval needed

# ✅ GOOD: Use /commit skill
# User types: /commit
# → All git commands auto-approved for this turn
```

### 2. Enable Plan Mode for Planning

```python
# ❌ BAD: Manual approval for every plan update
agent.input("Plan the implementation")
# → edit("PLAN.md", "# Step 1") - approval needed
# → edit("PLAN.md", "# Step 2") - approval needed
# → edit("PLAN.md", "# Step 3") - approval needed

# ✅ GOOD: Enable plan mode
agent.is_planning = True
agent.input("Plan the implementation")
# → All edit calls auto-approved
```

### 3. Approve for Session in Development

```python
# ❌ BAD: Approve "once" for development workflow
agent.input("Run tests")
# → Approve "once"

agent.input("Run linter")
# → Approve "once" (annoying!)

agent.input("Run formatter")
# → Approve "once" (very annoying!)

# ✅ GOOD: Approve "session" for development
agent.input("Run tests")
# → Approve "session"

agent.input("Run linter")
# → Auto-approved ✓

agent.input("Run formatter")
# → Auto-approved ✓
```

### 4. Use Specific Patterns in Skills

```yaml
# ❌ BAD: Too permissive
tools:
  - bash  # All bash commands!

# ✅ GOOD: Specific patterns
tools:
  - Bash(git status)
  - Bash(git diff *)
  - Bash(git commit *)
```

### 5. Deny Dangerous Operations

```python
# Destructive operation
agent.input("Delete all migration files")
# → bash("rm -rf migrations/") - approval needed
# → User selects "Deny"
# → Future delete attempts also blocked
```

## Security Considerations

### Skills Are One-Turn Only

```python
# Turn 5: /commit
# → permission_scope set (turn=5)
# → git commands auto-approved

# Turn 6: User continues conversation
# → permission_scope cleared
# → git commands require approval again
```

This prevents accidental permission escalation.

### Plan Mode Is Explicit

```python
# Agent CANNOT set is_planning itself
agent.is_planning = True  # Must be set by user/framework
```

Only the calling code can enable plan mode - agent can't escalate permissions.

### Session Memory Is Scoped

```python
# Approval only lasts for current session
# New session = new approval needed
```

User decisions don't persist across sessions.

### Tool Approval Is Final Layer

Even with all auto-approval mechanisms, dangerous tools not covered by other layers still require explicit user approval.

## Related Documentation

- [Skills](skills.md) - Pre-packaged workflows with scoped permissions
- [Tool Approval](../useful_plugins/tool_approval.md) - Web-based approval plugin
- [Plugins](plugins.md) - Plugin system overview
- [Events](events.md) - Event hooks for custom permission logic
