# Wiki page skill evals

Benchmarks for the two skills that write the pages people open most:
`wiki-page-person` and `wiki-page-project`. The material is synthetic. Every
name, address and number is made up, and the starting pages are written by
the Wiki's own mapper (`Notebook.stub_person` / `stub_project`).

```sh
cd examples/wiki-skill-evals
co benchmark check wiki-person
co eval run wiki-person  --agent agent.py --skill wiki-page-person  --invoke explicit --runs 2 --max-iterations 15
co eval run wiki-project --agent agent.py --skill wiki-page-project --invoke explicit --runs 2 --max-iterations 15
co eval run wiki-project-sessions --agent agent.py --skill wiki-project-sessions --invoke explicit --runs 2 --max-iterations 15
python .co/benchmarks/check_pages.py        # the production validator on every page written
```

`.co/skills/` links to the skills in `connectonion/useful_skills/`, so an edit
there is what the next run tests.

`wiki-project-sessions` (#1943) writes a project page from nothing but the
messages the user typed to their coding agents. Its six cases: a project with a
clear arc, a decision reversed, a folder that was only ever exploration, two
unrelated topics in one folder, a password pasted in a message (in
`forbidden.txt`, so `check_pages.py` fails the page if it appears anywhere), and
an update that gets only the messages since the page was last written.

`wiki-person-search` (#1943 stage 3) investigates a person by searching an
evidence folder instead of reading one material file. Its fixtures were made
by the production code (`people_evidence.materialize`): `page.md`,
`coverage.md` and `evidence/` with `index.md` and one file per mail. Six
cases: a phone number in one signature among thirteen mails (the needle), two
people named Mia (the other one only in a coding message), a forwarded mail
with a third party's claims, a mail carrying instructions to an AI, a single
calendar invitation, and an update that gets only the new mail.

```sh
co eval run wiki-person-search --agent agent.py --skill wiki-person-search --invoke explicit --runs 2 --max-iterations 30
```

## What the two checks cover

- `co eval` judges what a reader would see: facts from the material, nothing
  from the wrong person or from a forwarded third party, no instruction taken
  from a mail, no deployment claimed from a plan, no secret copied, a
  workspace not mistaken for a project. Its judge sees the first 4,000
  characters of the answer.
- `check_pages.py` runs every page the agent wrote through the Wiki's own
  pipeline (`normalize_numbered_sources` → `restore_runner_fields` →
  `validate`), which is what decides whether a real investigation's page is
  saved or refused. It also checks the whole page for strings in a fixture's
  `forbidden.txt`.

## Limits

- `co eval` drives a ConnectOnion Agent on its default model. Production
  runs these skills under Codex, so compare runs of this benchmark with each
  other, never with a production run.
- One or two runs a case measure direction, not a rate.

## Results, 2026-09-28 (co/gemini-3.8-flash, 15 steps an attempt)

| run | change | person | project | pages the validator accepts |
|---|---|---|---|---|
| base | — | 3/6 (3 out of steps) | 3/5 (2 out of steps) | — |
| v1 | "read the input, then write; no hunting for examples" | 5/6 | 4/5 | 6/6 person, 1/5 project |
| v3 | validator accepts box-drawing flows and `[1, 2]` | 5/6 | 5/5 | 11/11 once fixture ids matched production |
| v6 | cases isolated (fresh `out/`), "write once, check once, stop" | 12/12 attempts | 9/10 | 11/11 |
| v7 | "Where it stands" names the date of the last activity | — | 10/10 attempts | 11/11 |

Every failure in the baseline was the agent running out of steps: it read the
page and the material in two steps, then searched the workspace for example
pages, logs and other skills to copy a format from.
