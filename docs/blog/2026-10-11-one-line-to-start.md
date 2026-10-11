---
description: Installing co took four commands and a working Python. Now one line installs it in its own environment, sets up the identity and key, and tells Codex and Claude Code about it.
tags: [Install]
---

# One line to start

Until today, getting started with co meant four steps, and each one could go
wrong:

1. have Python 3.10 or newer;
2. `pip install connectonion`, which goes into whichever Python is first on
   your PATH, often the system one;
3. `co init`;
4. read a table of forty skills to see whether it had worked.

Now it is one line, the way oh-my-zsh installs:

```bash
curl -fsSL https://raw.githubusercontent.com/openonion/connectonion/main/install.sh | sh
```

## What the line does

- If you have no [uv](https://docs.astral.sh/uv/), it installs it first.
- `uv tool install connectonion` puts co in an environment of its own and
  `co` on your PATH. uv downloads a Python if you have none, so the first
  requirement is gone. Your system Python is never touched.
- `co init --yes` creates your agent identity and an OpenOnion key with
  starter credit, links the co skills into Codex and Claude Code, and writes
  co's command index into their `AGENTS.md` / `CLAUDE.md`.
- It ends with what to try next: `co status`, `co auth google`,
  `co auth microsoft`.

`CO_VERSION=1.9.2b10` in front of `sh` installs a preview instead of the
stable release.

## Measured

On a machine with no uv, starting from an empty home directory:

| | Time | Result |
|---|---|---|
| Linux (Parrot) | 8 s | co 1.9.1, identity, $5.00 credit |
| macOS | 33 s | co 1.9.2b8, identity, credit, Codex and Claude Code index |

## Smaller

`co init` used to print a table of every skill it linked, forty rows by two
columns, so the lines that mattered scrolled away. It now prints one line per
coding agent, naming any skill folder of your own that it left alone.
`co skills link` still prints the full table.

## Not yet

Windows needs its own one-liner in PowerShell (`irm … | iex`). It comes next,
once it has run on a real Windows machine.
