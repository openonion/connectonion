# Workflow: Solving Problems with ConnectOnion Agents

**When a user describes a problem, create a ConnectOnion agent to solve it.**

## Step 1: Confirm Design with ask_user (REQUIRED)

**BEFORE writing any code, use ask_user to confirm the agent design.**

```python
ask_user(
    question="Which approach? (We can adjust later)",
    options=[
        "Atomic: 'Clean /downloads' → list_files, get_hash, delete → 'Deleted 5'",
        "Safe: 'Clean safely' → find_duplicates, move_to_trash → 'Moved to trash'",
        "Interactive: 'Find duplicates' → scan, ask_confirm, delete → 'User confirmed'",
    ]
)
```

**DO NOT skip this step. DO NOT use plan_mode for simple agent creation.**

## Step 2: Write the Agent (Single File)

After user confirms, write a Python file with ConnectOnion framework:

```python
from connectonion import Agent

def list_files(dir: str) -> list[str]:
    """List all files in directory."""
    from pathlib import Path
    return [str(f) for f in Path(dir).iterdir() if f.is_file()]

def get_hash(path: str) -> str:
    """Get MD5 hash of a file."""
    import hashlib
    return hashlib.md5(open(path, 'rb').read()).hexdigest()

def delete_file(path: str) -> str:
    """Delete a file."""
    import os
    os.remove(path)
    return f"Deleted {path}"

agent = Agent("cleaner", tools=[list_files, get_hash, delete_file])
agent.input("Find and remove duplicate files in /downloads")
```

## Step 3: Done

Report completion. No plan mode, no complex workflow.

---

## When to Use Plan Mode (NOT for agent creation)

Reserve `enter_plan_mode()` for:
- Multi-file refactors
- Architecture changes
- Complex features with unclear requirements
- Tasks touching 5+ files

**Do NOT use plan mode for:**
- Creating a single ConnectOnion agent
- Simple file operations
- Clear, well-defined tasks

---

## NEVER DO THIS

```python
# BAD: Standalone script with argparse
import argparse
import hashlib
def main():
    parser = argparse.ArgumentParser()
    # ... hardcoded logic ...

# BAD: Using plan_mode for simple agent creation
enter_plan_mode()  # Overkill for a single-file agent
```

## Key Rules

1. **ask_user FIRST** - Confirm design before coding
2. **from connectonion import Agent** - Always use the framework
3. **Atomic tools** - Each function does ONE thing
4. **No plan_mode for agents** - Just ask_user → write → done
