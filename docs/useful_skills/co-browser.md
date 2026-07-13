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

The skill teaches the agent the full `co browser` lifecycle:

1. **Identity** — set `CO_WHO` so the daemon can attribute tabs
2. **Solo vs concurrent** — bare commands on `main`, or `tab open` + `-t <name>` when a second agent exists
3. **Direct functions vs `do`** — deterministic steps are free; natural language costs LLM calls
4. **Evidence** — screenshot/`get_text` verification, one-shot rule for irreversible actions
5. **Exit codes** — branch on `0/1/2/3/4` instead of parsing prose

## Why a Skill

`co browser` errors are self-documenting (an exit-4 tells the agent exactly how to
open its own tab), but a skill front-loads the lifecycle so the agent gets it right
on the first command instead of learning from collisions:

- Sets identity before touching the browser
- Opens its own tab when the board shows another agent
- Uses direct functions for deterministic steps, saving `do` for judgment
- Screenshots before/after irreversible actions and never double-clicks submit

## Key Commands

```bash
co browser go_to example.com          # navigate (daemon auto-starts, window visible)
co browser get_text                   # page text
co browser do "extract the pricing"   # AI agent drives the same live browser
co browser tab ls                     # who is running what
co browser status                     # daemon health, headless flag, the board
co browser close                      # shut everything down
```

## See Also

- [co browser](../co-browser.md) — full CLI reference (tabs, contention, daemon)
- [CLI Browser](../cli/browser.md) — dispatch rules and function discovery
- [Built-in Skills](README.md) — all copyable skills
