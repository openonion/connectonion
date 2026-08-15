---
name: cli-skill-design
description: Design a `co <thing>` CLI surface and its SKILL.md together so an agent can drive it without guessing — every command ends by naming the next one, `--help` lists everything, and every failure says what to run instead. Use when adding a new CLI command group, writing or rewriting a SKILL.md for one, or auditing an existing one.
---

# Designing a CLI skill

A CLI skill is two files that have to agree: the command surface (`co <thing> ...`)
and the `SKILL.md` that tells an agent how to drive it. Design them together —
the agent's whole world is *what it types* and *what comes back*.

`co-browser` is the worked example. Read it before you write anything: its exit-code
table, its "read the output, not just the exit code" rule, and its Done checklist are
what this methodology generalizes. (Building a skill that drives a *website* through
`co browser`? That is the sibling skill `browser-workflow-skill-builder` — DOM,
selectors, verification scripts. This one is about the command surface itself.)

Two properties. Each has a test you run and paste the result of — not a principle
you assert in the PR.

## (a) Tip-tested discoverability

**Rule:** every command execution — success *and* failure — ends by naming the next
command, spelled out, with the argument shape filled in.

```
Read one with: co gmail read <#>        ✅ names the command
See the docs for more options            ❌ names nothing
```

### The tip test

A tip is good if an agent that has *only that tip* makes the right next call. That
is testable, so test it:

```python
from connectonion import llm_do

llm_do(
    f"You just ran a shell command. Its full output was:\n\n{out}\n\n"
    "Your goal: read the newest email. Reply with ONE shell command and nothing else.",
    model="co/gemini-3.7-flash",
)
```

Use a **text-only** call (`llm_do`), not `co ai`. An agent with a shell will run the
command it picks — measured: the first attempt at this test executed `co gmail read 1`
and then `co auth google` against a real account. You are grading the reply, not the
mailbox.

- **Pass** — the reply is a command that exists and advances the goal (`co gmail read 1`).
- **Fail** — it invents a name (`co gmail open 1`), asks for help, or replies with prose.

Rules for the harness, or the result means nothing:
- Give it the **output only**. No `SKILL.md`, no `--help`, no conversation history —
  those are exactly the crutches the tip exists to replace.
- Pin the model so a rerun compares like with like.
- Run it per command, not once. Score the whole surface in a table and paste it
  into the PR:

  | command | tip printed | goal given to the fresh agent | it replied | pass |
  |---|---|---|---|---|

- Anything that fails: fix the tip, not the test.

### What makes a tip pass

- It contains the **literal command name**, not a description of it.
- Placeholders say where the value comes from: `<#> from this listing`, not `<id>`.
- **The tip survives piping.** Agents always pipe. A tip inside
  `if console.is_terminal:` is invisible to every caller that needs it, and manual
  testing never catches it because a human runs in a terminal. Check every one:

  ```bash
  co <thing> <cmd> | cat        # the tip must still be there
  ```

- **One** next step. Two tips is a fork, and the agent resolves a fork by guessing.
- Failures get tips too, and the tip is the fix (see (b)).

Measured on the mail surface (8 tips, `co/gemini-2.5-flash`, 2026-08): 5 passed. The
three failures are the three rules above, each in its pure form —

- a piped listing prints **no** tip, and the model invented `readmail 18f2a`;
- `Retry the same command with --idempotency-key <key>` never names the command, and
  the model replied `!! --idempotency-key k-123`;
- `run co gmail to refresh` stops one step short of the goal, and the model replied
  `co gmail && co gmail 3` — a command that does not exist.

A tip that reads fine to a human fails this test. That is the point of running it.

## (b) Self-diagnosing, self-correcting execution

### Rule 1 — `--help` enumerates every capability

An agent that cannot find a command from `--help` will invent one, and an invented
command name costs a round trip every time. So: no hidden commands, no capability
that only `SKILL.md` knows about.

**Check it, both directions:**

```bash
g=<thing>
# every subcommand the CLI has
co $g --help | sed -n '/─ Commands/,$p' | grep -oE '^│ [a-z-]+' | awk '{print $2}' | sort -u
# every command the skill mentions
grep -oE "co $g [a-z-]+" SKILL.md | awk '{print $3}' | sort -u
```

Diff the two lists. Every CLI command must be either documented or deliberately
skipped (say which, and why, in the PR). Every command the skill mentions must
exist — a skill naming a command that `--help` does not list is a documentation bug,
and it is the failure mode this check exists to catch.

Repeat one level down for command groups (`co outlook contact --help`).

### Rule 2 — every error path is a fix-it guide

The exit code says *what kind* of problem; the text says *what to run*. Both, every
time. Follow `co-browser`'s contract: a small, stable set of codes, and a table in
`SKILL.md` whose right-hand column is a command, not an adjective.

**Check it by producing each row.** For every exit code your surface can return,
write down the command that provokes it and run it:

```bash
co <thing> <cmd-that-fails>; echo "exit=$?"
```

Then assert two things about the output: it names the cause, and it names a command
to run next. Paste the reproduction table into the PR:

| exit | provoked by | printed | names a next command |
|---|---|---|---|

If a row cannot be provoked, you do not know that it behaves as documented — say so
rather than documenting it.

### Rule 3 — say so when failure exits 0

Some commands print `❌ Failed` and still exit `0`. That is fine as long as the
skill says it loudly, because an agent that chains `cmd && next` on such a surface
walks straight past the failure. Where any failure exits 0, `SKILL.md` opens with
co-browser's rule:

> **Always read the output, not just the exit code.**

and the exit-code table has a row for "exit 0, error text on stdout".

## Progressive disclosure

The skill is read top to bottom by an agent that wants to act now.

1. **Routing first** — if several commands could serve the request, the first
   section is the table that picks one. Wrong-command errors are the expensive kind.
2. **The 80% commands next**, as copy-pasteable lines.
3. **The gotchas that change a result** — the ones that make an agent report
   something false if it doesn't know them (stale numbering, prefix-only search,
   silent export-on-download). Not trivia.
4. **Errors and recovery last.** By then the agent is only here because something
   broke.

Everything else belongs in `--help`. If the skill is restating `--help`, delete it
from the skill: two copies drift, and the copy in the skill is the one that goes
stale.

## Honesty rule

Document only what you have run. Every command, flag, and exit code in a `SKILL.md`
must have been verified against the code or `--help` on the branch you are writing
against — not remembered, and not planned. Behavior that is designed but unshipped
gets a dated "not yet — today it works like this" note, never a present-tense
sentence. An agent cannot tell aspiration from fact, and it pays for the difference
with a failed run.

## Done checklist

- [ ] Routing table first, if more than one command could serve the request
- [ ] Every command in the skill exists in `--help` (diffed, both directions)
- [ ] Every command prints one next-step tip, and the tip survives `| cat`
- [ ] Tip test run per command, results table in the PR
- [ ] Exit-code table present, right column is a command
- [ ] Every exit code provoked at least once, reproduction table in the PR
- [ ] "Read the output, not just the exit code" stated if any failure exits 0
- [ ] Gotchas that change a reported result are written down
- [ ] Nothing documented that was not run
