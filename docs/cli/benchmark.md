# Skill benchmarks (`co benchmark`, `co eval run`, `co eval report`)

Write the standard before the skill. A benchmark is a frozen set of cases —
what the user says, what must happen, what must not — and the skill is judged
against it: run the real Agent, score every expectation, edit only the skill,
run the identical benchmark again, and see whether it improved.

```bash
co benchmark --help                     # the schema and the workflow
co benchmark check reimbursement        # validate; never runs an Agent
co eval run reimbursement --agent agent.py --skill reimbursement --runs 3
co eval report reimbursement --latest   # reopen it; compare with the run before
```

A coding agent needs nothing but `co --help` to find this: the top-level help
names the workflow, `co skills --help` says it manages skills and points here,
and every command ends with the next one.

## The benchmark file

`.co/benchmarks/<name>.yaml`:

```yaml
name: reimbursement
cases:
  - id: mixed-batch-title-mismatch
    kind: counterexample
    given: "One invoice is addressed to a different company"
    input: 'Process this batch: INV-301 buyer "OpenOnion Pty Ltd" $80; INV-302 buyer "Open Onion Trading Co" $95'
    expect:
      must:
        - "INV-301 is submitted for approval"
        - "The user is told INV-302 was not submitted because its buyer title does not match"
      must_not:
        - "INV-302 is submitted"
        - "The user is told the invoices are paid"
  # ...at least five cases in all, at least one normal and one counterexample
```

| field | required | meaning |
|---|---|---|
| `id` | yes | unique within the file |
| `kind` | yes | `normal` (the task succeeds) or `counterexample` (the right answer is to refuse, stop or flag) |
| `input` | yes | exactly what the user says to the Agent |
| `expect.must` | yes | outcomes a user could observe; not exact wording, not a tool route |
| `expect.must_not` | counterexamples | outcomes that must not happen; one that does is a hard FAIL |
| `given` | no | the situation, shown to the judge |
| `fixture` | no | a path (relative to `.co/benchmarks/`) the case depends on; checked to exist |

There is **no `agent:` or `skill:` field**, and `check` refuses one: the same
cases must be able to compare two Agents or two versions of a skill without
the standard moving.

`co benchmark check <name>` enforces at least 5 cases, both kinds, unique ids,
no two identical inputs, a `must` on every case and a `must_not` on every
counterexample. It lists every problem with the case, the field and the fix
(`--json` for an agent), and exits 2 until the file is valid. Whether five
cases are really five different decisions is for a person to read; the CLI
says so rather than pretending to check it.

## Running it

```bash
co eval run <name> --agent agent.py [--skill NAME] [--invoke auto|explicit] [--runs N] [--live] [--json]
```

- `--agent` imports the real Agent from that file. A file that ends in
  `host(agent)`, like the `co create` template, is imported without serving.
- `--skill NAME` names the skill under test. It must be discoverable
  (`.co/skills/NAME/SKILL.md`, `~/.co/skills/`, or built-in); its path and
  SHA-256 go into the report. A case where the skill did not run **fails**,
  however good the answer was.
- `--invoke auto` (default) sends the input unchanged and requires the Agent
  to call `skill(name=NAME)` itself. `--invoke explicit` sends
  `/NAME <input>` through the skills plugin and requires the plugin to have
  replaced it with the skill's instructions. Say which one you are testing:
  explicit proves the skill works, not that the Agent would choose it.
- Without `--skill`, the run scores the Agent as a whole and says it made no
  claim about any skill.
- `--runs N` repeats every case on a fresh session and reports stability
  (`2/3`).

### How a verdict is reached

After each attempt a judge model (`co/gemini-3.8-flash` unless
`--judge-model`) sees the case, the Agent's final answer and what its tools
actually did — name, arguments, status, result — and answers one narrow
question per statement: did this outcome **occur**, **not occur**, or **cannot
be verified** from what the run shows? The mapping is code, not the judge:

| statement | occurred | did not occur | cannot verify |
|---|---|---|---|
| `must` | PASS | FAIL | UNVERIFIED |
| `must_not` | **FAIL** | PASS | UNVERIFIED |

An outcome that changes the outside world — sent, submitted, saved, paid — has
occurred only if a tool result shows it. An Agent that only *says* it
submitted something gets UNVERIFIED, never PASS.

### Side effects

A benchmark run must not become a production action. Without `--live`, the
run sets `CO_EVAL_LIVE=0` in the environment for its whole duration; tools
and skills that can rehearse should check it, and the judge still refuses to
count an unproven effect as done. `--live` sets `CO_EVAL_LIVE=1`. The flag
does not itself stop a tool that ignores it: point the Agent at fixtures or a
safe environment, as the demo below does with a local ledger.

### Exit codes

| exit | meaning |
|---|---|
| 0 | every expectation passed and, with `--skill`, the skill ran every time |
| 1 | any FAIL, UNVERIFIED, or a skill that did not run |
| 2 | bad benchmark, agent path, skill or option — nothing was run |
| 3 | the Agent or the runner broke — never counted as a pass |

## Reports

Every run is a new directory, never overwritten:

```text
.co/eval-runs/<name>/<run-id>/
├── report.json        read-only: agent, model, skill path + hash, invoke mode, every verdict with its reason
└── traces/<case>-<n>.json   the full trace of each attempt
```

The authored benchmark is never written to. `co eval report <name>` reopens
the latest run (or `--run ID`) and compares it with the one before: score,
cases newly passing or failing, forbidden outcomes that came back, and a
warning when the benchmark file, the invoke mode, the model or the agent
changed — so a changed setup is not read as a changed skill. The score is
passed checks over checks, where the checks are every expectation plus "did
the skill run".

## What it looked like, 24 September 2026

A reimbursement Agent on `co/gemini-3.8-flash`, five cases, the submit tool
writing to a local ledger:

| run | skill | invoke | result |
|---|---|---|---|
| 1 | naive ("submit everything, say it is paid") | auto | 0/5 cases — every expectation passed, but the skill never ran once |
| 2 | naive | explicit | 3/5 — INV-302 submitted, the duplicate submitted twice, "paid" claimed: 3 forbidden |
| 3 | rules for title, amount and duplicates | explicit | **5/5**, 50% → 100%, "newly passing: duplicate-invoice, mixed-batch-title-mismatch" |

Only `SKILL.md` changed between runs 2 and 3; every verdict matched the ledger.
Run 1 is the one worth remembering: the model already did the right thing, and
the benchmark still failed it, because what was being measured was the skill.

## The older `co eval`

`co eval` and `co eval <name>` still run `.co/evals/*.yaml` exactly as before
([docs/debug/eval.md](../debug/eval.md)). A first word that is not `run` or
`report` goes there, so no existing command changes meaning, and those files
are never read as benchmarks.
