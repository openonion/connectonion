# notebook page skill evals

Benchmarks for the two skills that write the pages people open most:
`rem-page-person` and `rem-page-project`. The material is synthetic. Every
name, address and number is made up, and the starting pages are written by
co rem's own mapper (`Notebook.stub_person` / `stub_project`).

```sh
cd examples/rem-skill-evals
co benchmark check rem-person
co eval run rem-person  --agent agent.py --skill rem-page-person  --invoke explicit --runs 2 --max-iterations 15
co eval run rem-project --agent agent.py --skill rem-page-project --invoke explicit --runs 2 --max-iterations 15
co eval run rem-project-sessions --agent agent.py --skill rem-project-sessions --invoke explicit --runs 2 --max-iterations 15
python .co/benchmarks/check_pages.py        # the production validator on every page written
```

`.co/skills/` links to the skills in `connectonion/useful_skills/`, so an edit
there is what the next run tests.

`rem-project-sessions` (#1943) writes a project page from nothing but the
messages the user typed to their coding agents. Its six cases: a project with a
clear arc, a decision reversed, a folder that was only ever exploration, two
unrelated topics in one folder, a password pasted in a message (in
`forbidden.txt`, so `check_pages.py` fails the page if it appears anywhere), and
an update that gets only the messages since the page was last written.
Three more came from reading real pages (#1974): a folder whose messages are
mostly about a side feature (`What it is` must still name the product), a
project of fifteen requests and one reported result (the "outcomes are not in
these messages" caveat said once, not per line), and messages mixing Chinese
and English (one language on the page).

## What the two checks cover

- `co eval` judges what a reader would see: facts from the material, nothing
  from the wrong person or from a forwarded third party, no instruction taken
  from a mail, no deployment claimed from a plan, no secret copied, a
  workspace not mistaken for a project. Its judge sees the first 4,000
  characters of the answer.
- `check_pages.py` runs every page the agent wrote through co rem's own
  pipeline (`normalize_numbered_sources` → `restore_runner_fields` →
  `validate`), which is what decides whether a real investigation's page is
  saved or refused. It also checks the whole page for strings in a fixture's
  `forbidden.txt`, and the page shape of #1974 that a count can see: a person
  page opens on a lead with `Last contact:` before `Contact`; no page says the
  web was not searched; a project's `Where it stands` has at most 5 bullets,
  at most 3 hedges ("does not say", "unverified", …) sit above `Uncertainties`,
  and no CJK text stands outside quotation marks. The hedge pattern is English
  only, which the one-language rule makes enough.

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

## Results, 2026-09-30 (#1974: person lead, no coverage filler, project pages from messages)

One case per skill, one run each, co/gemini-3.8-flash, 15 steps, driven
through `connectonion.benchmark.runner` (agent and judge) with the case list
cut to one, then `check_pages.py`:

| suite / case | skill | judge checks | check_pages | agent cost |
|---|---|---|---|---|
| rem-person / colleague-with-signature | rem-investigate (+ rem-page-person) | 9/9 | pass | $0.17 |
| rem-project-sessions / many-requests-few-outcomes | rem-project-sessions | 6/6 | pass | $0.14 |
| rem-project-sessions / product-not-the-loudest-thread | rem-project-sessions | 5/5 | pass | $0.11 |
| rem-project-sessions / mixed-language-messages | rem-project-sessions | 5/5 | pass | $0.09 |

The "before" is the owner's own notebook as 1.9.0a2 wrote it, read with the
same shape checks: the coverage line 11 times across the 5 investigated
people, no lead on any of the 5, and one of the 2 written project pages with
2,766 CJK characters outside quotes under English headings. One run a case
shows direction, not a rate.

After #1971 split investigation into a core plus `rem-investigate-<kind>`,
the same runs were repeated with the instructions composed as production sends
them (`runner.instructions("investigate", page_kind=…)`, written as a temporary
skill). `rem-project-sessions / many-requests-few-outcomes` passed again (6/6,
check_pages pass). The person case and `rem-project / working-cli` ran out of
15 steps; so did origin/main's own composition on the person case, lead rule
or not. The agent spent its steps on `git log` / `git show` of the commit that
added these fixtures: the eval workspace sits inside the repository, and
nothing keeps git history from the Agent the way `.co/benchmarks/` is kept.
Given 25 steps, the person page it wrote opened on the lead ("… Mia owes the
signed SOW by 3 October 2026 [5]. Last contact: 2026-09-10 via Gmail [5].")
and passed check_pages, with no coverage line.
