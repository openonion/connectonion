# Shell

Shell command execution tool.

## Usage

**Option 1: Import directly**

```python
from connectonion import Shell

agent = Agent("coder", tools=[Shell()])
```

**Option 2: Copy and customize**

```bash
co copy shell
```

```python
from tools.shell import Shell  # Your local copy
```

## Installation

```python
from connectonion import Shell

shell = Shell()
```

## API

### run(command)

Execute a shell command, returns output.

```python
result = shell.run("ls -la")
# Returns: "total 12\ndrwxr-xr-x  8 user staff..."

result = shell.run("git status")
# Returns: "On branch main\nnothing to commit..."

result = shell.run("python --version")
# Returns: "Python 3.11.0"
```

Pass `timeout=<seconds>` for long-running work. The value is honored without a
hidden ten-minute cap. If it expires, `subprocess.TimeoutExpired` is raised so a
caller or agent can distinguish the timeout from successful output.

### run_in_dir(command, directory)

Execute command in a specific directory.

```python
result = shell.run_in_dir("npm install", "/path/to/project")
# Returns: "added 100 packages..."

result = shell.run_in_dir("pytest", "/path/to/tests")
# Returns: "5 passed in 0.5s"
```

## Output limit

Output is capped at 10,000 characters to prevent token overflow. The `STDERR:`
label and the `Exit code:` line are the tool's own, and they are never cut — so
a long failing command does not read as a truncated success.

When a command writes more than the cap, the budget is spent in this order:

1. `Exit code:` — kept whole.
2. stderr — gets the space first, because it is the part a caller acts on.
3. stdout — whatever is left.

Each stream that overflows ends with a note of what was dropped, e.g.
`... (stderr truncated, 12,000 total chars)`. When both streams overflow, each
keeps enough budget for its own note, so a large stderr cannot drop stdout
without saying so.

## Use with Agent

```python
from connectonion import Agent, Shell

shell = Shell()
agent = Agent("coder", tools=[shell])

agent.input("list all python files in current directory")
# Agent runs: shell.run("ls *.py")

agent.input("run the tests")
# Agent runs: shell.run("pytest")

agent.input("install requests package")
# Agent runs: shell.run("pip install requests")
```

## Common Use Cases

```python
# Git operations
shell.run("git status")
shell.run("git add .")
shell.run("git commit -m 'update'")

# Package management
shell.run("pip install requests")
shell.run("npm install express")

# Build and test
shell.run("pytest")
shell.run("npm run build")

# System info
shell.run("pwd")
shell.run("whoami")
shell.run("df -h")
```

## Customizing

Need to modify Shell's behavior? Copy the source to your project:

```bash
co copy shell
```

Then import from your local copy:

```python
# from connectonion import Shell  # Before
from tools.shell import Shell      # After - customize freely!
```
