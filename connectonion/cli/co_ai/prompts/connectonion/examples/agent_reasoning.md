# Principle: Agent Reasons, Tools Act

**ConnectOnion agents are Python files (.py), NOT markdown files.**

<good-example>
# GOOD: Create a Python file like /tmp/my_agent.py
from connectonion import Agent

def list_files(dir: str) -> list[str]: ...
def get_hash(path: str) -> str: ...
def delete(path: str) -> str: ...

agent = Agent("cleaner", tools=[list_files, get_hash, delete])
agent.input("Remove duplicate files")
</good-example>

<bad-example>
# BAD: Don't create markdown files for ConnectOnion agents
# This is Claude Code format, NOT ConnectOnion:
# /tmp/.claude/agents/cleaner.md  <- WRONG
</bad-example>

**Give tools, not logic. Let the agent decide strategy.  NEVER create standalone scripts with hardcoded logic**

<good-example>
# GOOD: Atomic tools, agent reasons
def list_files(dir: str) -> list[str]: ...
def get_hash(path: str) -> str: ...
def delete(path: str) -> str: ...

agent = Agent("cleaner", tools=[list_files, get_hash, delete])
agent.input("Remove duplicate files in /downloads")
# Agent decides: list -> hash -> compare -> delete duplicates
</good-example>

<bad-example>
# BAD: Logic in Python, agent just executes
def clean_duplicates(dir: str) -> str:
    seen = {}
    for f in Path(dir).iterdir():
        h = hash(f)
        if h in seen:
            f.unlink()  # Hardcoded: delete second occurrence
        seen[h] = f
    return "Done"

agent = Agent("cleaner", tools=[clean_duplicates])
agent.input("Clean")  # No reasoning, just runs function
</bad-example>

<bad-example>
# BAD: Tool does the reasoning, not the agent
def scan_for_duplicates(dir: str) -> dict:
    """Scan and find all duplicates."""  # Tool decides what's duplicate
    ...

def delete_duplicates(dir: str, strategy: str = "keep_newest") -> str:
    """Delete duplicates with strategy."""  # Tool decides which to keep
    ...

# Agent just calls these - no reasoning about WHICH files to delete
</bad-example>
