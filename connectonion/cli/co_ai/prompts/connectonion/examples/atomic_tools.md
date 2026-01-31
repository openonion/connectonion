# Principle: Tools Should Be Atomic

**Each tool does one thing. Agent composes them.**

<good-example>
# GOOD: Single-purpose tools
def read_file(path: str) -> str: ...
def write_file(path: str, content: str) -> str: ...
def list_dir(path: str) -> list[str]: ...

# Agent composes: list -> read -> modify -> write
</good-example>

<bad-example>
# BAD: Tool does too much
def process_files(dir: str, pattern: str, action: str, recursive: bool, backup: bool) -> str:
    for f in glob(pattern):
        if backup: copy(f)
        if action == "delete": delete(f)
        elif action == "compress": compress(f)
    return "Done"

# Too many params, too many paths, agent can't reason about steps
</bad-example>
