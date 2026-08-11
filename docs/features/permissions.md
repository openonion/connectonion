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
│ 1. Template Permissions - Explicit built-in allowlist      │
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
│ 5. Tool Approval - Resolve unpermitted operations          │
│    Local/admin operator → explicit approval                │
│    Hosted non-admin requester → reject without a dialog    │
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

# Template-permitted tools - auto-approved
agent.input("Read the README")
# → read_file auto-approved (template permission) ✓

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

# Unpermitted operations - operator approval or fail closed
agent.input("Delete all files")
# → Local/admin operator: approval required
# → Hosted non-admin requester: rejected without a dialog
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

## 1. Template Permissions - Explicit Built-In Allowlist

The standard host template explicitly permits its built-in read-only tools. The permission entries use `source: safe`; safety does not come from a tool being absent from a denylist.

```yaml
permissions:
  "read_file":
    allowed: true
    source: safe
    reason: read-only operation
    expires:
      type: never
```

These named tools need no approval. A custom or dynamically registered tool is not implicitly safe just because its name is new.

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

## 5. Tool Approval - Ask User for Unpermitted Operations

With live IO, the web approval UI handles every tool call that did not match an explicit template, config, skill, user, or mode permission. Known effectful tools remain documented for discoverability, but that list is not the security boundary.

### Known Effectful Tools

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
3. Local/admin operator receives an approval request
   ┌──────────────────────────────────┐
   │ ⚠️ Approval needed: bash         │
   │                                  │
   │ Command: rm -rf /tmp/cache       │
   │                                  │
   │ [Approve once]                   │
   │ [Approve for session]            │
   │ [Deny]                           │
   └──────────────────────────────────┘
4. Operator decides (a hosted non-admin is rejected before this step)
   ↓
5. Tool executes (or blocked)
```

### Implementation

```python
@before_each_tool
def check_approval(agent):
    """Check if tool needs approval before execution."""

    pending = agent.current_session['pending_tool']
    tool_name = pending['name']
    tool_args = pending['arguments']
    requester = agent.current_session.get('requester')

    # 1. Check skill permission scope (highest priority)
    scope = agent.current_session.get('permission_scope')
    if scope and scope['turn'] == agent.current_session['turn']:
        if _matches_pattern(tool_name, tool_args, scope['allowed_tools']):
            return  # Auto-approve

    # 2. Check explicit template/config/skill permissions
    permissions = agent.current_session.get('permissions', {})
    if matches_permission(tool_name, tool_args, permissions):
        return  # Auto-approve

    # 3. Check session memory
    approved_tools = agent.current_session.get('approval', {}).get('approved_tools', {})
    if tool_name in approved_tools and approved_tools[tool_name] == 'session':
        return  # Auto-approve

    # 4. Check if denied
    if tool_name in approved_tools and approved_tools[tool_name] == 'deny':
        raise ToolDenied(f"{tool_name} was denied")

    # 5. Fail closed: only the local/admin operator may approve
    if requester and requester.get('level') != 'admin':
        raise ToolDenied(f"{tool_name} requires operator approval")

    agent.io.send({
        'type': 'approval_needed',
        'tool': tool_name,
        'arguments': tool_args,
    })
    response = agent.io.receive()

    if not response.get('approved', False):
        raise ToolDenied(f"User denied {tool_name}")

    if response.get('scope', 'once') == 'session':
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
   ├─ Hosted non-admin requester → REJECT without a dialog
   └─ Local/admin operator → ASK USER (web approval UI)
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
# Scenario 1: Template-permitted tools
# ────────────────────────────────────────────────────────
agent.input("Find all tests")
# → glob("**/test_*.py") - template permission ✓
# → read_file("test_agent.py") - template permission ✓

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
# Scenario 3: Session memory (remember user decisions)
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
# Scenario 5: Unpermitted operations (operator approval or fail closed)
# ────────────────────────────────────────────────────────
agent.input("Create new config file")
# → write("config.json", ...) - REQUIRES APPROVAL
# → User approves "once"
# → Executes this time only
# → A hosted non-admin requester is rejected without a dialog instead

agent.input("Create another file")
# → write("data.json", ...) - REQUIRES APPROVAL again
```

## Flow Diagram

```
Agent wants to use a tool
          │
          ▼
Explicit template, config, skill,
user, or session permission?
    ├─ yes → execute
    └─ no
          │
          ▼
No live IO?
    ├─ yes → execute
    └─ no
          │
          ▼
Operator-owned mode bypass?
(`ulw`, or `accept_edits` for named edit tools)
    ├─ yes → execute
    └─ no
          │
          ▼
Hosted non-admin requester?
    ├─ yes → reject without a dialog
    └─ no  → ask the local/admin operator
                 ├─ once → execute once
                 ├─ session → save permission and execute
                 └─ deny → reject
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

### 2. Approve for Session in Development

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

### 3. Use Specific Patterns in Skills

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

### 4. Deny Dangerous Operations

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

### Session Memory Is Scoped

```python
# Approval only lasts for current session
# New session = new approval needed
```

User decisions don't persist across sessions.

### Tool Approval Is Final Layer

Even with all auto-approval mechanisms, every remaining live-IO tool requires an operator decision. A local/admin operator receives the approval dialog; a hosted non-admin requester is rejected without one. Unknown plugin and protocol-provided tools fail closed too.

## Related Documentation

- [Skills](skills.md) - Pre-packaged workflows with scoped permissions
- [Tool Approval](../useful_plugins/tool_approval.md) - Web-based approval plugin
- [Plugins](../concepts/plugins.md) - Plugin system overview
- [Events](../concepts/events.md) - Event hooks for custom permission logic
