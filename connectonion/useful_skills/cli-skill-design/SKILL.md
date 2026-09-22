---
name: cli-skill-design
description: Design a `co <thing>` CLI surface and its SKILL.md together so an agent can drive it without guessing — help teaches the workflow and serves as the skill source of truth, every command names the next step, and failures explain recovery. Use when adding a new CLI command group, writing or rewriting a SKILL.md for one, or auditing an existing one.
---

# Designing a CLI skill

Design command help as a usage skill for both people and agents. The help page
is the source of truth for choosing and using a command: purpose, inputs,
procedure, effects, verification and recovery. An agent should be able to learn
correct usage from help, execute a command, and continue from its actual output.

Keep one authored workflow definition. Render terminal help and, where supported,
a loadable Skill from that definition. Derive command names, arguments, defaults
and required flags from the CLI registration. Author workflow and evidence
requirements explicitly; function signatures alone cannot explain them. A
separate SKILL.md can route to relevant help and add domain judgment without
maintaining a second copy of command syntax. This is a design requirement, not
a claim that an existing CLI already generates Skills from its help.

`co-browser` is the worked example. Read it before you write anything: its exit-code
table, its "read the output, not just the exit code" rule, and its Done checklist are
what this methodology generalizes. (Building a skill that drives a *website* through
`co browser`? That is the sibling skill `browser-workflow-skill-builder` — DOM,
selectors, verification scripts. This one is about the command surface itself.)

Start with the help workflow contract below, then verify command discovery,
execution and recovery. Record actual test results, not just design principles.

## Help is the usage skill

### Design each help page around a task

Put the common workflow before the option catalog. A useful page answers:

| Part | What help must teach |
|---|---|
| Purpose | When to choose this command and which related command serves a different goal |
| Inputs | What is required, how to discover real IDs/paths/names, and how ambiguity is resolved |
| Procedure | The minimal ordered commands, using examples verified on the current branch |
| Effects | What is read, written, sent or scheduled; whether a model is called; prerequisites and actual authorization behavior |
| Results | What output means, including empty, partial, failed and no-change results |
| Verification | How to inspect the result and evidence; what a successful exit does not establish |
| Recovery | Concrete commands for missing inputs, ambiguous matches, unavailable sources and failures |
| Next step | How to choose the next action from observed output and when to stop |

A group help page routes goals to workflows and lists all capabilities. Detailed
command help supplies the procedure and options only when needed. Human-readable
output is the default; expose structured output explicitly when supported and
show the real flag placement. Do not document a JSON or export flag that the
command does not implement.

Examples must explain where argument values come from. Prefer a discovery
command that lists actual records and prints a copyable next command. Where
useful, invoking a command without its required selection can show choices
without starting work. A fictional example filename is not an existing record;
never make the user or agent guess it. Explain that --help displays help and
exits even when other arguments are supplied, if that is the CLI's behavior.

Preserve the full path from intent to evidence:

```text
Goal → discover command → read relevant help → discover inputs
     → execute → inspect output → verify → continue, recover or stop
```

Load progressively: group help first, then the selected command's help. Keep
unrelated command detail out of the agent's context. If a Skill artifact is
required, generate it from the same workflow definition or make it a thin entry
point to help. Verify that help and any generated Skill agree with the registered
CLI; do not build an independent documentation dialect.

### Test help as an agent input

Keep these checks separate from the output-only tip test below:

1. **Help-only command selection.** Give a fresh text-only model one rendered
   help page and a goal. Provide no separate Skill, implementation code or
   conversation history. Ask for the next command and grade whether it exists,
   uses supported flags and advances the goal. Use llm_do, with no tools; never
   execute these replies. Include first run, existing data, missing/ambiguous
   inputs, safe previews, failures and structured output where supported.
2. **Workflow completion.** In a separate controlled test, give an agent only
   the goal, access to CLI help and command outputs. Use synthetic fixtures and
   isolated state; restrict execution to the fixture CLI and test dependencies.
   Check that it discovers real inputs, completes the task, verifies evidence
   and stops or recovers correctly. Do not connect production accounts, send
   messages or install background jobs as a side effect of testing guidance.

Pin the model and fixtures, retain outputs and define acceptance before the run.
Allocate enough response tokens for a complete command, including quoted paths.
If a harness limit truncates a response, retain it as an incomplete evaluation
and document any allowance change. For genuine command-selection failures,
improve the help; do not weaken the goal or grader to make the result pass.

Report the two kinds of evidence separately:

| Help page / workflow | Goal | Model and fixture | Observed choice or result | Verification | Pass / failure |
|---|---|---|---|---|---|

A correct command choice does not prove workflow completion. A zero exit code
does not prove factual quality. If only help selection was tested, say so;
identify untested execution or recovery paths instead of calling the whole skill
validated. Where there is no PR, retain this report with the local change.

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
    model="co/gemini-3.8-flash",
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

Both help and the Skill are read by an agent that wants to act now. Apply the
same ordering to the shared workflow definition:

1. **Routing first** — if several commands could serve the request, the first
   section is the table that picks one. Wrong-command errors are the expensive kind.
2. **The 80% commands next**, as copy-pasteable lines.
3. **The gotchas that change a result** — the ones that make an agent report
   something false if it doesn't know them (stale numbering, prefix-only search,
   silent export-on-download). Not trivia.
4. **Errors and recovery last.** By then the agent is only here because something
   broke.

Detailed options belong in the relevant command help. Put reusable usage
knowledge in the shared help definition; let the Skill route to it or render
from it. Keep separately authored Skill content focused on domain judgment.
Avoid two manually maintained copies of the same workflow.

## Honesty rule

Document only what you have run. Every command, flag, and exit code in a `SKILL.md`
must have been verified against the code or `--help` on the branch you are writing
against — not remembered, and not planned. Behavior that is designed but unshipped
gets a dated "not yet — today it works like this" note, never a present-tense
sentence. An agent cannot tell aspiration from fact, and it pays for the difference
with a failed run.

## Done checklist

- [ ] Help teaches purpose, observed inputs, procedure, effects, results, verification and recovery before listing options
- [ ] Help and any loadable Skill share one workflow definition or the Skill explicitly routes to help
- [ ] Command syntax/defaults match CLI registration; generated Skill exports are verified if implemented
- [ ] Help-only command-selection tests run with a pinned model; results and failures retained
- [ ] Controlled help-and-output-only workflow completion tested, or execution coverage explicitly marked untested

- [ ] Routing table first, if more than one command could serve the request
- [ ] Every command in the skill exists in `--help` (diffed, both directions)
- [ ] Every command prints one next-step tip, and the tip survives `| cat`
- [ ] Tip test run per command, results table in the PR
- [ ] Exit-code table present, right column is a command
- [ ] Every exit code provoked at least once, reproduction table in the PR
- [ ] "Read the output, not just the exit code" stated if any failure exits 0
- [ ] Gotchas that change a reported result are written down
- [ ] Nothing documented that was not run
