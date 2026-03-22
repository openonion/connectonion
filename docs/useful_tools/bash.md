# bash

Execute bash commands from an agent. Returns stdout + stderr as a string.

Unix/Mac only. For cross-platform use, see [Shell](shell.md).

## Usage

```python
from connectonion import Agent, bash

agent = Agent("coder", tools=[bash])

agent.input("run the tests")
agent.input("install dependencies from requirements.txt")
agent.input("show git log for the last 5 commits")
```

## API

```python
bash(command, description, cwd=".", timeout=120)
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `command` | str | required | Bash command to run |
| `description` | str | required | What the command does (shown to user, not passed to shell) |
| `cwd` | str | `"."` | Working directory |
| `timeout` | int | `120` | Seconds before timeout (max 600) |

Returns stdout + stderr as a string.

## Examples

```python
from connectonion import bash

# Basic commands
bash("ls -la", "List files")
bash("git status", "Check git status")
bash("python --version", "Check Python version")

# With working directory
bash("npm install", "Install packages", cwd="/path/to/project")
bash("pytest", "Run tests", cwd="./my-module")

# With longer timeout
bash("npm run build", "Build project", timeout=300)
```

## Direct Call (without agent)

```python
from connectonion import bash

result = bash("git log --oneline -5", "Recent commits")
print(result)
# abc1234 Add feature
# def5678 Fix bug
# ...
```

## Use with Agent

```python
from connectonion import Agent, bash

agent = Agent("devops", tools=[bash])

agent.input("check if port 8000 is in use")
# → bash("lsof -i :8000", ...)

agent.input("run pytest and show any failures")
# → bash("pytest -v", ...)

agent.input("commit all changes with message 'update docs'")
# → bash("git add . && git commit -m 'update docs'", ...)
```

## Combining with FileTools

`bash` and `FileTools` are a common pair — file tools for reading/editing, bash for running:

```python
from connectonion import Agent, bash
from connectonion.useful_tools.file_tools import FileTools

agent = Agent("coder", tools=[FileTools(), bash])

agent.input("read main.py, fix the import error, then run python main.py to verify")
```

## Notes

- Output is truncated at 10,000 characters to prevent token overflow
- stdout and stderr are merged in the returned string
- Non-zero exit codes are included in the output (`Exit code: 1`)
- Windows is not supported — use [Shell](shell.md) for cross-platform

## See Also

- [Shell](shell.md) — class-based shell tool, cross-platform
- [FileTools](file_tools.md) — read/edit files
- [Terminal](terminal.md) — interactive terminal UI
