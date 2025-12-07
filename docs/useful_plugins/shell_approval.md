# shell_approval

Prompts for user approval before executing shell commands.

## Quick Start

```python
from connectonion import Agent, Shell
from connectonion.useful_plugins import shell_approval

shell = Shell()
agent = Agent("assistant", tools=[shell], plugins=[shell_approval])

agent.input("Clean up temp files")
# ┌─ Shell Command ─────────────────┐
# │ rm -rf /tmp/test                │
# └─────────────────────────────────┘
# Execute this command?
#   ❯ Yes, execute
#     Auto approve 'rm' in this session
#     No, tell agent what I want
```

## Safe Commands (No Approval)

Read-only commands are auto-approved:

```
ls, ll, cat, head, tail, less, more
grep, rg, find, fd, which, whereis
file, stat, wc, pwd, echo, date
whoami, id, env, uname, hostname
df, du, free, ps, top, tree
git status, git log, git diff, git show
npm list, pip list, python --version
```

## Approval Options

When prompted, you can:

1. **Yes, execute** - Run once
2. **Auto approve '{cmd}'** - Auto-approve this command type for session
3. **No, tell agent what I want** - Provide feedback

## Events

| Handler | Event | Purpose |
|---------|-------|---------|
| `_check_approval` | `before_each_tool` | Check and prompt for approval |

## Session Data

- `agent.current_session['shell_approved_cmds']` - Set of auto-approved command types
