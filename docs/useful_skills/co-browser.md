# co-browser

Drive one persistent, logged-in browser from the shell with `co browser` — solo or with multiple agents sharing it.

## Install

```bash
co copy co-browser
# → .co/skills/co-browser/SKILL.md
```

## Usage

```
/co-browser open github and screenshot my notifications
```

## What the Skill Teaches

`co browser`'s errors are self-documenting (an exit-4 tells the agent exactly how
to open its own tab), but a skill front-loads the lifecycle so the agent gets it
right on the first command instead of learning from collisions:

1. **Identity** — attach `CO_WHO` to every command (shell state doesn't survive between tool calls)
2. **The board** — check `status` / `tab ls` before claiming; one task = one tab; `-t <name>` on every command when concurrent
3. **Right verb** — direct functions for deterministic steps (free, instant), `do "<end state>"` only for judgment, text probes before screenshot probes
4. **Evidence** — read output text (soft failures return exit 0 with the error on stdout), screenshots at irreversible-action gates only, one-shot submits
5. **Login** — human logs in in the visible window; the agent polls with short bounded waits and never touches credentials

For the full command reference — tabs, contention, daemon lifecycle, exit codes —
see [co browser](../co-browser.md); `co browser help` prints the live function list.

## See Also

- [co browser](../co-browser.md) — canonical CLI reference
- [CLI Browser](../cli/browser.md) — dispatch rules and function discovery
- [Built-in Skills](README.md) — all copyable skills
