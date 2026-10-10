---
description: co init now tells Codex and Claude Code that co exists, in the one file they read every session. Codex went from 0 of 3 to 3 of 3 on a Linear question.
tags: [CLI, Agents, Skills]
---

# The agent that did not know `co` existed

Aaron asked Codex to hand a task to Ody. Nothing happened. Codex was not
being stubborn; it had no reason to think there was anything to hand it
*with*. `co` was installed on that Mac, linked skills and all, and
`~/.codex/AGENTS.md` did not mention it once.

We had seen this before in our own harness. `co ai`, asked about a Linear
board with no rule in its prompt, opened a browser in 3 of 3 runs. One rule
("use co linear") and it used `co linear` in 3 of 3. The commands were
there, and the agent was never told they existed.

Skills did not help, and the reason is easy to miss. A skill is loaded when
the agent already suspects it needs one. Codex asked about Linear does not go
looking for a skill called `co-linear`. It runs `command -v linear`, finds
nothing, and asks you to connect Linear.

## One file every session reads

Both tools have one file they load on every turn: `~/.codex/AGENTS.md` and
`~/.claude/CLAUDE.md`. So `co init` now writes a block there, between
`<!-- co:begin 1.9.2 -->` and `<!-- co:end -->`. Three rules, then one line
per top-level command:

```
- You have `co`, the ConnectOnion CLI. Below is every top-level command.
- For outside services, handing work to someone or another machine, or memory:
  run `co commands` and read `co <cmd> --help` before using a browser or writing a script.
- Don't look for credentials yourself: run the command; if a key is missing, it says how to add it.

co linear — Linear issues from the terminal, with your personal API key: ...
```

The list is generated from the Typer app, not written by hand, so it cannot
promise a command that is gone. Hidden and deprecated commands are left out.
Subcommands stay behind `--help`, which is the whole point: the block says
where to look, and the CLI explains the rest. It came to 56 lines and about
1,060 tokens.

## Did it work?

We ran Codex on "What's open on my Linear board?" from an empty folder, with
a throwaway `CODEX_HOME` that held only a copy of the login and config, so
the real `~/.codex` was never touched. The only difference between the two
arms was the block.

| | used `co linear` | browser | answered |
|---|---|---|---|
| without the block | 0 of 3 | 0 of 3 | 0 of 3: "connect Linear" |
| with the block | 3 of 3 | 0 of 3 | 3 of 3: 4 open issues |

Without the block, Codex checked `PATH` for a `linear` binary, grepped the
empty folder, once asked its plugin store for a Linear app, and gave up.
With it, every run started with `co commands`, read `co linear --help`, and
listed the board.

## Keeping it true after an upgrade

A block that names last month's commands is worse than none. Nobody re-runs
`co init` after `pip install -U`, but their agent does start again. So
`host()` (and `co ai`, which calls it) reads the version stamp at startup
and rewrites the block only when it is missing or stale, printing one line
per file it changed. When the stamp is current it only reads two small files,
which took about a millisecond. A full regeneration took 0.9 seconds and
happens once per upgrade.

There are two things it never does. It never creates `~/.codex` or `~/.claude`.
A server with no person on it has neither, so a `co deploy --to` host or a
CI box is left alone without any special case. It also never changes a byte
outside the markers, and a test checks exactly that. `co doctor` reports a
missing or stale block, and `co skills index --remove` takes it out.

The lesson is the one #2113 started with. Installing a capability is not the
same as an agent knowing about it. The agent needs to hear about it in the
one place it always reads.
