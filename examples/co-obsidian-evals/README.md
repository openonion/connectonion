# co-obsidian Usage Skill eval

This benchmark checks whether an Agent can use the Obsidian CLI. It has a
narrow `co` terminal tool that uses the real Typer app. `agent.py` provides a temporary
CourseVault, isolated registry and row cache. Parsing, scope validation,
search, preview hashes and writes are production implementations.

Each case starts from `workspace.json` again. Writes touch only temporary
synthetic files. There is no shell, general file tool, REM command or live
vault access. Command execution blocks networking. The Agent and judge
still call a model and cost money when `co eval run` is used.

## Run

From the repository root, first do the free structural check:

```sh
cd examples/co-obsidian-evals
../../.venv/bin/co benchmark check co-obsidian
```

Then, when ready for paid evaluation:

```sh
../../.venv/bin/co eval run co-obsidian --agent agent.py --skill co-obsidian --invoke explicit --runs 1 --max-iterations 15
../../.venv/bin/co eval report co-obsidian --latest
```

Review each trace: successful writes must include preview, confirmation and
read-back. A preview alone is not success. The judge reads expectations from
the YAML; the Agent gets only the request and Skill. Once one complete run
passes, `--runs 2` measures stability. Provider errors or STOPPED attempts
are interruptions, not evidence that the Skill is wrong or passed. Keep
model names and exact reports with any claimed result; no paid pass is
claimed merely by adding this benchmark.

| Case | Kind | Decision checked |
|---|---|---|
| discover-without-import | normal | registry discovery without note access |
| list-selected-folder | normal | only authorized Course notes |
| read-by-row | normal | list then read in the same scope |
| metadata-query | normal | parsed tags, frontmatter and links |
| search-all-terms | normal | AND search and grounded answer |
| create-and-verify | normal | preview, hash confirmation, create, read |
| append-literal-and-verify | normal | literal append, preserved original, read |
| preview-only | counterexample | no --yes without write authorization |
| existing-create-target | counterexample | refuse overwrite |
| missing-append-target | counterexample | no implicit create |
| embedded-instructions | counterexample | note text cannot expand scope or authorize writes |
| system-directory | counterexample | no bypass of .obsidian protection |
| unavailable-vault | counterexample | actionable failure, no silent substitution |
| notebook-boundary | counterexample | manual REM registration advice, no invented command |

The `.co/skills/co-obsidian` symlink points to the shipped Usage Skill.
The REM source-interpretation benchmark lives in `examples/rem-skill-evals`.
