# Permissions

ConnectOnion provides multiple permission mechanisms to balance safety and automation. This guide explains how they work together.

## Unified Permission System

**Core Concept**: All permissions use a single, consistent data structure at runtime. Whether from config files, skills, or user approvals, every permission is stored the same way in `session['permissions']`.

```python
# All permissions use this unified format:
session['permissions'] = {
    "tool_name": {
        "allowed": True,
        "source": "config"|"skill"|"user"|"safe",
        "reason": "description",
        "when": {"param": "pattern"},  # Optional: granular matching
        "expires": {"type": "never"|"turn_end"|"session_end"}
    }
}
```

**Key Insight**: You don't need to understand 5 different permission formats - everything becomes this unified structure at runtime.

## Permission Layers

```
┌─────────────────────────────────────────────────────────────┐
│ 1. SAFE_TOOLS - Always auto-approved                       │
│    read_file, glob, grep (read-only operations)            │
│    Stored as: source='safe', expires='never'               │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│ 2. Config Permissions - Project-level auto-approve         │
│    host.yaml: Bash(git status), write(*.md), etc.          │
│    Stored as: source='config', expires='never'             │
│    Pattern: Bash() → 'bash' with when:{command: '...'}     │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│ 3. Skills - Temporary scoped permissions (one turn)         │
│    /commit → auto-approve git commands for this turn only  │
│    Stored as: source='skill', expires='turn_end'           │
│    Preserves user approvals via snapshot/restore           │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│ 4. User Approvals - Tool-level session memory              │
│    User approves 'bash' once → ALL bash commands allowed   │
│    Stored as: source='user', expires='session_end'         │
│    **TOOL-LEVEL**: Approving "bash npm" = approve ALL bash │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│ 5. Tool Approval - Ask user for dangerous operations       │
│    bash, edit, write → require explicit user approval      │
│    If no permission in unified dict → ask user             │
└─────────────────────────────────────────────────────────────┘
```

### Tool-Level vs Command-Specific Approvals

**Critical**: User approvals are **tool-level**, not command-specific. This is different from config/skill permissions.

```python
# Config/Skill permissions can be granular:
session['permissions']['bash'] = {
    "source": "config",
    "when": {"command": "git status"}  # Only matches "git status"
}

# User approvals are tool-level:
session['permissions']['bash'] = {
    "source": "user",
    "reason": "approved for session"
    # NO 'when' field - matches ALL bash commands
}
```

**Why?** User approvals prioritize convenience for development workflows. If you approve "bash", you trust bash commands for the session. Config/skills use granular matching for safety.

## Quick Start

```yaml
# .co/host.yaml - Configure project-level permissions
permissions:
  "Bash(git status)":
    allowed: true
    source: config
    reason: safe git read
    expires:
      type: never
  "write":
    allowed: true
    source: config
    reason: safe doc edits
    when:
      file_path: "*.md"
    expires:
      type: never
```

```python
from connectonion import Agent, host
from connectonion.useful_tools import bash, write, read_file
from connectonion.useful_plugins import skills, tool_approval

def create_agent():
    return Agent(
        "assistant",
        tools=[bash, write, read_file],
        plugins=[skills, tool_approval]
    )

host(create_agent)  # Loads permissions from .co/host.yaml

# Safe tools - always auto-approved
agent.input("Read the README")
# → read_file auto-approved (SAFE_TOOLS) ✓

# Config permissions - auto-approved from host.yaml
agent.input("Check git status")
# → Bash(git status) auto-approved (config permission) ✓

agent.input("Update the docs")
# → write(file_path="docs/guide.md") auto-approved (config permission with match) ✓
# → write(file_path="src/main.py") requires approval (doesn't match *.md) ✗

# Skills - scoped permissions
# User types: /commit
# → git commands auto-approved for this turn only ✓
# → Turn ends, permissions cleared ✓

# Session memory - remember decisions
agent.input("Run tests")
# → bash("pytest") approval needed (first time, not in config)
# → User approves for "session"
# → Future pytest calls auto-approved for this session ✓

# Dangerous operations - always ask
agent.input("Delete all files")
# → User approval required (destructive operation)
```

## Unified Permission Format

All permission sources (config, skills, user, safe) use the same runtime structure:

```python
session['permissions'] = {
    "tool_name": {
        "allowed": bool,             # Allow or block
        "source": str,               # Where it came from
        "reason": str,               # Why it was granted
        "when": dict,                # Optional: parameter matching
        "expires": dict              # When it expires
    }
}
```

### Config Files Use Bash() Pattern

**User-facing config** (in `.co/host.yaml`):
```yaml
permissions:
  "Bash(git status)":  # User-friendly pattern
    allowed: true
    source: config
    reason: safe git read
    expires:
      type: never
```

**Runtime format** (internal):
```python
session['permissions']['bash'] = {
    "allowed": True,
    "source": "config",
    "reason": "safe git read",
    "when": {"command": "git status"},  # Converted to 'when' field
    "expires": {"type": "never"}
}
```

**Conversion happens automatically** - you write `Bash(git status)` in config, it becomes `bash` with `when:{command: "git status"}` at runtime.

### Tool-Level User Approvals

When users approve tools during execution, approval is **tool-level**:

```python
# User approves "bash npm install" → Stored as:
session['permissions']['bash'] = {
    "allowed": True,
    "source": "user",
    "reason": "approved for session",
    # NO 'when' field → matches ALL bash commands
    "expires": {"type": "session_end"}
}
```

**Why tool-level?**
- Convenience: Approving once means trusting the tool for session
- Development workflow: Don't re-approve every npm/pytest/git command
- Clear intent: "I trust bash" vs "I only trust this specific command"

**Security**: Config and skills can use granular `when` field. User approvals are simpler.

### Snapshot/Restore Pattern (Skills)

Skills preserve user approvals using snapshot/restore:

```python
# Before skill:
permissions = {"write": {source: "user", ...}}

# During skill:
snapshot = deepcopy(permissions)  # Save user approvals
permissions["bash"] = {source: "skill", when: {command: "git *"}, ...}  # Add skill perms

# After skill:
permissions = snapshot  # Restore - user's 'write' preserved, skill's 'bash' cleared
```

**Result**: Skills grant temporary permissions without losing user approvals.

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
# → glob("**/*.py") - auto-approved ✓
# → read_file("main.py") - auto-approved ✓
```

## 2. Config Permissions - Project-Level Auto-Approve

Permanent permissions defined in `.co/host.yaml` that auto-approve safe commands without asking each time.

### Configuration

Add permissions to your `host.yaml`:

```yaml
# .co/host.yaml
trust: careful
port: 8000

# Auto-approve safe commands
permissions:
  # Simple tool name - matches any call
  "read_file":
    allowed: true
    source: config
    reason: safe read operation
    expires:
      type: never

  # Exact bash command
  "Bash(git status)":
    allowed: true
    source: config
    reason: safe read-only git command
    expires:
      type: never

  # Wildcard matching - command prefix
  "Bash(git diff *)":
    allowed: true
    source: config
    reason: safe git diff commands
    expires:
      type: never

  # Parameter matching - only specific files
  "write":
    allowed: true
    source: config
    reason: safe documentation edits
    when:
      file_path: "*.md"
    expires:
      type: never
```

### Pattern Types

**1. Simple Tool Name**
```yaml
"read_file":
  allowed: true
  source: config
  reason: safe read operation
  expires:
    type: never
```
Matches any call to `read_file` with any parameters.

**2. Exact Bash Command**
```yaml
"Bash(git status)":
  allowed: true
  source: config
  reason: safe git read
  expires:
    type: never
```
Only matches exact command `git status`.

**3. Wildcard Bash Command**
```yaml
"Bash(git diff *)":
  allowed: true
  source: config
  reason: safe git diff
  expires:
    type: never
```
Matches any command starting with `git diff ` (e.g., `git diff HEAD`, `git diff --staged`).

**4. Parameter Matching**
```yaml
"write":
  allowed: true
  source: config
  reason: safe doc edits
  when:
    file_path: "*.md"
  expires:
    type: never
```
Matches `write` calls only when `file_path` ends with `.md`.

### Unified Permission Structure

All permissions use the same structure:

```yaml
"pattern":
  allowed: true|false          # Whether to allow
  source: config|user|skill|safe|default  # Where it came from
  reason: "description"        # Why it was granted (shown in logs)
  when:                       # Optional: parameter-level matching
    param_name: "pattern"
  expires:
    type: never|session_end|turn_end  # When it expires
```

### Priority Order

When multiple permissions could match:

1. **Runtime approvals** (`source: user`) - highest priority
2. **Config permissions** (`source: config`) - from host.yaml
3. **Default permissions** (`source: default`) - built-in safe tools
4. **Safe tools** (`source: safe`) - read-only operations

### Parameter Matching Examples

**Write to specific directories:**
```yaml
"write":
  allowed: true
  source: config
  reason: safe doc edits
  when:
    file_path: "docs/**/*.md"
  expires:
    type: never
```

**Edit in specific paths:**
```yaml
"edit":
  allowed: true
  source: config
  reason: safe config edits
  when:
    file_path: "*.{yaml,yml,json}"
  expires:
    type: never
```

**Bash with timeout limits:**
```yaml
"bash":
  allowed: true
  source: config
  reason: safe short commands
  when:
    timeout: "30000"  # Exact match on timeout parameter
  expires:
    type: never
```

### Bash Command Chain Validation

Config permissions support **bash command chains** using bashlex parser. When agent executes `pwd && ls -F`, ALL commands must be permitted.

**How it works:**
1. Parse chain with bashlex: `"pwd && ls -F"` → `["pwd", "ls"]`
2. Check each command against permissions
3. Auto-approve only if ALL commands are whitelisted

**Example - All permitted:**
```yaml
permissions:
  "Bash(pwd)": {allowed: true, ...}
  "Bash(ls *)": {allowed: true, ...}
```
Command: `pwd && ls -F` → ✅ Auto-approved (both permitted)

**Example - Partial permission:**
```yaml
permissions:
  "Bash(pwd)": {allowed: true, ...}
  # rm NOT whitelisted
```
Command: `pwd && rm -rf /` → ❌ Requires approval (rm not permitted)

**Supported constructs:**
- AND: `cmd1 && cmd2`
- OR: `cmd1 || cmd2`
- Pipe: `cmd1 | cmd2`
- Semicolon: `cmd1; cmd2`

**Security:** One dangerous command = whole chain rejected.

### Common Workflows

**Development Agent:**
```yaml
permissions:
  "Bash(git status)":
    allowed: true
    source: config
    reason: safe git read
    expires:
      type: never
  "Bash(git diff *)":
    allowed: true
    source: config
    reason: safe git diff
    expires:
      type: never
  "Bash(pytest *)":
    allowed: true
    source: config
    reason: safe test execution
    expires:
      type: never
```

**Documentation Agent:**
```yaml
permissions:
  "write":
    allowed: true
    source: config
    reason: doc updates
    when:
      file_path: "docs/**/*.md"
    expires:
      type: never
  "edit":
    allowed: true
    source: config
    reason: doc updates
    when:
      file_path: "docs/**/*.md"
    expires:
      type: never
```

**Code Review Agent (read-only):**
```yaml
permissions:
  "read_file":
    allowed: true
    source: config
    reason: code review
    expires:
      type: never
  "glob":
    allowed: true
    source: config
    reason: find files
    expires:
      type: never
  "grep":
    allowed: true
    source: config
    reason: search code
    expires:
      type: never
```

### Best Practices

✅ **DO:**
- Auto-approve safe read-only commands (`git status`, `git log`)
- Use parameter matching for file operations (`*.md`, `docs/**/*`)
- Keep `source: config` and `expires: never` for permanent rules
- Add descriptive `reason` fields for debugging

❌ **DON'T:**
- Auto-approve destructive commands (`rm -rf`, `git push --force`)
- Use wildcards too broadly (`Bash(*)` matches everything)
- Auto-approve all bash without `match` field
- Forget to test patterns with actual tool calls

### Example

```python
# .co/host.yaml has:
# permissions:
#   "Bash(git status)":
#     allowed: true
#     source: config
#     ...

from connectonion import Agent, host
from connectonion.useful_tools import bash

def create_agent():
    return Agent("dev-assistant", tools=[bash])

host(create_agent)  # Loads permissions from .co/host.yaml

# Later, in conversation:
agent.input("Check git status")
# → Bash(git status) - auto-approved (config permission) ✓
# → No approval prompt shown to user

agent.input("Run npm install")
# → Bash(npm install) - requires approval ✗
# → User sees approval prompt (not in config)
```

## 3. Skills - Temporary Scoped Permissions with Snapshot/Restore

Pre-packaged workflows with **one-turn** automatic tool approval that preserves user approvals.

### How It Works - Unified Permissions

```python
# Turn 3: User approved "write" for session (tool-level)
session['permissions'] = {
    "write": {
        "allowed": True,
        "source": "user",
        "reason": "approved for session",
        "expires": {"type": "session_end"}
    }
}

# Turn 5: User types /commit
# Step 1: Take snapshot of current permissions
snapshot = deepcopy(session['permissions'])  # Preserves write approval

# Step 2: Grant skill permissions (adds bash with 'when' field)
session['permissions'] = {
    "write": {  # Preserved from snapshot
        "allowed": True,
        "source": "user",
        "reason": "approved for session",
        "expires": {"type": "session_end"}
    },
    "bash": {  # Added by skill (with granular matching)
        "allowed": True,
        "source": "skill",
        "reason": "commit skill (turn 5)",
        "when": {"command": "git *"},  # Only git commands
        "expires": {"type": "turn_end"}
    },
    "read_file": {  # Also added by skill
        "allowed": True,
        "source": "skill",
        "reason": "commit skill (turn 5)",
        "expires": {"type": "turn_end"}
    }
}

# During turn 5:
# → git status - auto-approved (skill permission matches "git *") ✓
# → git diff --staged - auto-approved (skill permission) ✓
# → git commit -m "msg" - auto-approved (skill permission) ✓
# → write("foo.txt") - auto-approved (user permission) ✓
# → pytest - BLOCKED (skill only allows "git *") ✗
# → rm -rf - BLOCKED (no permission) ✗

# Turn 5 ends (@on_complete)
# Step 3: Restore snapshot
session['permissions'] = snapshot  # User's write approval preserved ✓

# Turn 6: User continues
# → write - still works ✓ (user approval preserved)
# → git status - requires approval ✗ (skill permission cleared)
```

### Security Model with Snapshot/Restore

**Snapshot → Grant → Restore** - User approvals are never lost.

```
Turn 3: User approves "write" for session
  └─ permissions['write'] = {source: 'user', expires: 'session_end'}

Turn 5: /commit skill
  ├─ Snapshot current permissions (write saved)
  ├─ Grant skill permissions (bash with when:{command: 'git *'} added)
  ├─ Tools execute with both user + skill permissions
  └─ Turn ends → Restore snapshot
      └─ write preserved ✓
      └─ bash cleared ✓

Turn 6: Continue conversation
  ├─ write - still works (user approval)
  └─ bash - requires approval (skill cleared)
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

## 4. Plan Mode - Auto-Edit During Planning

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

## 5. Session Memory - Remember User Decisions

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

## 6. Tool Approval - Ask User for Dangerous Operations

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
    "bash": {
        "allowed": True,
        "source": "skill",
        "reason": "commit skill (turn 5)",
        "when": {"command": "git *"},  # Granular matching - only git commands
        "expires": {"type": "turn_end"}
    },
    "write": {
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
