# bash

Run a shell command and get its output back. Unix and macOS only — on Windows use
`terminal` instead.

```python
bash(command: str, description: str = "", cwd: str = ".", timeout: int = 120) -> str
```

| | |
|---|---|
| `command` | the command line to run |
| `description` | shown to the user instead of the raw command, when the raw command is noisy |
| `cwd` | working directory; defaults to where the agent is running |
| `timeout` | seconds before the command is killed. Default 120 |

## Use it for

Anything a shell does better than a dedicated tool: `git`, package managers,
build commands, one-off pipelines.

## Do not use it for

Reading, writing, searching or listing files. `read_file`, `write`, `grep` and
`glob` exist for those and return structured results the model can act on —
`bash("cat x.py")` gives you the same bytes with none of the handling. The
`prefer_write_tool` plugin blocks file creation through bash for this reason.

## Timeouts

A command that hits the timeout is killed and the output collected so far is
returned. Long builds need `timeout` raised deliberately rather than assumed.
