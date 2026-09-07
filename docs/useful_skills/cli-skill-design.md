# cli-skill-design

How to design a `co <thing>` CLI surface and its `SKILL.md` together, so an agent can drive it without guessing.

## Install

```bash
co copy cli-skill-design
# → .co/skills/cli-skill-design/SKILL.md
```

## Usage

```
/cli-skill-design
```

Use it when adding a new CLI command group, writing or rewriting a `SKILL.md` for one, or auditing an existing one.

## What it enforces

Two properties, each with a test you run and paste the result of — not a principle you assert:

**Tip-tested discoverability.** Every command execution, success or failure, ends by naming the next command. The test: give a fresh, text-only model *only* that output plus the goal, and ask for one shell command. If it invents a command name, the tip failed. Tips must also survive `| cat` — agents always pipe, and a tip hidden behind `console.is_terminal` is invisible to exactly the caller that needs it.

**Self-diagnosing execution.** `--help` enumerates every capability (diff it against the skill, both directions), every exit code is provoked at least once and its message names the command to run next, and any surface where a failure exits `0` says so at the top.

Plus the house rules: routing table first, gotchas that change a reported result, and nothing documented that was not run.

## Related

- [co-browser](co-browser.md) — the worked example this generalizes from
- [browser-workflow-skill-builder](browser-workflow-skill-builder.md) — the sibling for skills that drive a *website* through `co browser`

## Shared env contract (1.8.4 implementation)

New command groups must use the shared selected env, never discover cwd `.env`.
`co --env-file PATH <group> ...` is the explicit project selector; default reads
and writes use global `keys.env`. Keep process credentials separate from loaded
file values and resolve provider fields as whole account records. Test fresh
processes from root, nested and unrelated directories, including a project-only
non-OAuth variable that must stay absent by default.
