"""An invented notebook shaped like a real one, for the reader's design and browser tests.

Every person, company, project and source id here is made up. The pages follow
the templates the investigation stages write (rem-page-person, -project, -org,
-skill): a cited lead, Contact fields, Open threads naming who owes whom, a
dated History, numbered Sources, an ASCII Overview, a skill's Usage history.
Run logs are written relative to `now`, so "last night" is always last night.
"""

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from connectonion.rem.config import prepare
from connectonion.rem.files import Notebook


def _day(now: datetime, days_ago: int) -> str:
    return (now - timedelta(days=days_ago)).strftime("%Y-%m-%d")


def _people(now: datetime) -> dict:
    d = lambda n: _day(now, n)  # noqa: E731
    mara = f"""# Mara Ostrowski

Mara runs partnerships at [Fernhill Labs](../orgs/fernhill-labs.md) and is the user's main contact for the pilot [1][2]. The user owes her the signed data-sharing addendum, asked for on {d(9)} [4]; she owes the user the pilot's usage export [5]. Last contact: {d(1)}, email [6].

## Contact
- Email: mara@fernhill.example [1]
- Phone: Unknown
- Company: [Fernhill Labs](../orgs/fernhill-labs.md) [2]
- Role: Head of Partnerships [2]
- Signing entity: Unknown
- Handles: mara@fernhill.example [1]
- Language: English; Polish with colleagues [3]
- Also known as: M. Ostrowski [1]

## Who they are
- Head of Partnerships at Fernhill Labs, a twelve-person climate-data startup in Wellington [2].

## Why they are here
- She approached the user after a meetup talk on agent memory and asked for a pilot of co rem inside Fernhill's research team [3].

## Our relationship
- A paid pilot since {d(40)}: three seats, monthly invoice, renewal decision due at the end of the quarter [3][4]. She is direct, quick to escalate, and generous with feedback.

## History
- {d(40)}: pilot agreed; three seats from the following Monday [3].
- {d(26)}: first feedback call; asked for a shared notebook per team [4].
- {d(9)}: sent the data-sharing addendum for signature [4].
- {d(4)}: promised the usage export "by Friday" [5].
- {d(1)}: asked whether the renewal could include a fourth seat [6].

## Open threads
- **Data-sharing addendum** — the user has not signed it; with the user since {d(9)} [4].
- **Usage export** — she promised it by Friday ({d(4)}); unanswered since [5].

## How they communicate
- Short emails, bullet points, a deadline in the subject line [4][5].

## How the user writes to them
- Warm and brief; the user answers within a day [6].

## Cadence
- Roughly weekly, more often near invoices [4][6].

## Uncertainties
- Whether the fourth seat is budgeted or a wish.

## Sources
- [1] outlook:5c1e0a9b72d4 — address and signature; confidence high; observed {d(40)}.
- [2] outlook:9a03f1c2be77 — title and company in signature; confidence high; observed {d(40)}.
- [3] outlook:1b77de0c4f12 — how the pilot began; confidence high; observed {d(40)}.
- [4] outlook:e4a2c1907bd3 — addendum sent for signature; confidence high; observed {d(9)}.
- [5] outlook:77c09ad1e3f0 — export promised by Friday; confidence high; observed {d(4)}.
- [6] gmail:0f9be4c12a55 — fourth-seat question; confidence high; observed {d(1)}.

Investigation: mapped {d(41)} · investigated {d(0)} (outlook, gmail)
"""
    tomas = f"""# Tomás Reyes

Tomás is a former colleague who now reviews the user's conference talks [1]. Nothing open as of {d(3)}; next contact expected before the November deadline [2]. Last contact: {d(3)}, email [2].

## Contact
- Email: tomas.reyes@mailbox.example [1]
- Phone: Unknown
- Company: Unknown
- Role: Programme committee, Agents Summit [2]
- Language: Spanish; English for reviews [1]

## Our relationship
- Friendly and informal; he reads drafts, the user returns the favour [1].

## History
- {d(60)}: reviewed the user's spring talk [1].
- {d(3)}: confirmed he will review the next abstract [2].

## Open threads
- Nothing open as of {d(3)}; the next abstract goes to him before the November deadline [2].

## Sources
- [1] gmail:a1c3e5f7b9d2 — reviews and language; confidence medium; observed {d(60)}.
- [2] gmail:c4e6a8b0d2f1 — confirmation; confidence high; observed {d(3)}.

Investigation: mapped {d(70)} · investigated {d(2)} (gmail)
"""
    ines = f"""# Inès Halvorsen

Inès is the accountant who files the user's company returns [1]. Last contact: {d(12)}, email [1].

## Contact
- Email: ines@ledgerline.example [1]

## Open threads
- She is waiting on the user for the Q3 receipts; the user has owed them since {d(12)} [1].

## Sources
- [1] outlook:3d5f7b9e1a0c — receipts request; confidence high; observed {d(12)}.

Investigation: mapped {d(30)} · written {d(12)}
"""
    return {"people/mara-ostrowski.md": mara, "people/tomas-reyes.md": tomas, "people/ines-halvorsen.md": ines}


def _projects(now: datetime) -> dict:
    d = lambda n: _day(now, n)  # noqa: E731
    harbour = f"""# Harbour

## What it is
- A command-line tool that turns a team's shared inbox into a weekly brief, built for Fernhill's pilot [1].

## Overview
Mail is read once a night, grouped by thread, and summarised into one brief per team [1][2].

```text
 shared inbox ──read──> threads ──group──> team briefs
      │                                        │
      └──── attachments ──> extract ──┐        v
                                      └──> weekly brief ──> email
```

## Where it stands
- Observed {d(1)}. The nightly read and the grouping work on the pilot inbox; the brief still repeats long threads [2][3].
- Two of three pilot users opened last week's brief [3].

## Open threads
- Decide whether long threads are cut or summarised; the user owes Mara an answer before the renewal call [3].
- Waiting on Fernhill for a second test inbox; promised {d(6)} [4].

## Key decisions
- **{d(20)}:** one brief per team, not per person, to keep the email short [2].

## Paths
- /home/user/code/harbour [1]
- Sessions: 31
- First seen: {d(45)}
- Last seen: {d(1)}

## Sources
- [1] codex:7e1f0a2b3c4d — repository README; confidence high; observed {d(45)}.
- [2] claude-code:1a2b3c4d5e6f — design session; confidence high; observed {d(20)}.
- [3] outlook:9f8e7d6c5b4a — pilot feedback; confidence medium; observed {d(2)}.
- [4] outlook:4b5a6c7d8e9f — test inbox promised; confidence high; observed {d(6)}.

Investigation: mapped {d(45)} · investigated {d(0)} (codex, claude-code, outlook)
"""
    lantern = f"""# Lantern

## What it is
- A static site generator for the user's essays.

## Paths
- /home/user/code/lantern
- Sessions: 4
- Last seen: {d(33)}

Investigation: mapped {d(33)} · not investigated yet
"""
    return {"projects/harbour.md": harbour, "projects/lantern.md": lantern}


def _skill(name: str, count: int, last: str, what: str, mapped: str) -> str:
    usage = (f"- Invoked {count} times in your coding sessions in the last 180 days (412 session files: Codex, Claude Code), "
             f"last on {last} (Claude Code {count}). Counted by co rem from Skill tool calls.") if count else \
        "- No invocation found in your coding sessions in the last 180 days (412 session files: Codex, Claude Code)."
    return f"""# {name}

## What it does
{what}

## When to use
Unknown — not investigated yet

## Usage history
<!-- rem-usage -->
{usage}
<!-- /rem-usage -->

## Source
<!-- rem-installed-copies -->
- File: /home/user/.claude/skills/{name}/SKILL.md
- Discovery: claude-user
<!-- /rem-installed-copies -->

Investigation: mapped {mapped} · not investigated yet
"""


def _orgs_and_skills(now: datetime) -> dict:
    d = lambda n: _day(now, n)  # noqa: E731
    fernhill = f"""# Fernhill Labs

A climate-data startup in Wellington; the user's first paying pilot [1].

## Domains
- fernhill.example [1]

## Who they are
- Twelve people; research and data engineering [1].

## People here
- [Mara Ostrowski](../people/mara-ostrowski.md) — Head of Partnerships; owns the pilot [1]

## Open threads
- Renewal decision due at the end of the quarter; the user should send a proposal first [2].

## Sources
- [1] outlook:2c4e6a8b0d1f — signature and website; confidence high; observed {d(40)}.
- [2] outlook:6e8a0c2e4f6b — renewal timing; confidence high; observed {d(5)}.

Investigation: mapped {d(41)} · investigated {d(5)} (outlook)
"""
    pages = {"orgs/fernhill-labs.md": fernhill,
             "decisions/notebook-format.md": "# Notebook format\n\nPages stay Markdown so they can be read without co rem.\n"}
    for name, count, last, what in [("weekly-brief", 14, 1, "Write the Friday brief from the week's notebook changes."),
                                    ("invoice-check", 3, 9, "Check an invoice against the contract before it is sent."),
                                    ("talk-outline", 0, 0, "Turn an abstract into a talk outline with timings.")]:
        pages[f"skills/catalog/{name}.md"] = _skill(name, count, d(last), what, d(20))
    return pages


def _runs(now: datetime) -> list[dict]:
    """A week of nightly passes: quiet nights, one that stopped early, and last night's."""
    runs = []
    week = [(6, 12, [], "completed"), (5, 0, [], "completed"), (4, 31, ["projects/harbour.md"], "completed"),
            (3, 40, [], "failed"), (2, 18, ["people/tomas-reyes.md"], "completed"), (1, 9, [], "completed")]
    for days_ago, items, changed, outcome in week:
        start = (now - timedelta(days=days_ago)).replace(hour=3, minute=0, second=0, microsecond=0)
        runs.append({"started_at": start.isoformat(), "finished_at": (start + timedelta(minutes=14)).isoformat(),
                     "outcome": outcome, "items": items, "changed": changed, "sources": ["outlook", "gmail"],
                     "usage": {"input_tokens": 41000 * (items // 10 + 1), "output_tokens": 3100}, "seconds": 840})
    start = now - timedelta(hours=5)
    runs.append({"started_at": start.isoformat(), "finished_at": (start + timedelta(minutes=22)).isoformat(),
                 "outcome": "completed", "items": 46, "sources": ["outlook", "gmail", "codex"],
                 "changed": ["people/mara-ostrowski.md", "projects/harbour.md", "orgs/fernhill-labs.md"],
                 "usage": {"input_tokens": 212000, "output_tokens": 9400}, "seconds": 1320})
    return runs


def build(root: Path, now: datetime | None = None) -> Path:
    """Write the invented notebook at root and return it."""
    now = now or datetime.now(timezone.utc)
    prepare(root)
    notebook = Notebook(root)
    for record, text in {**_people(now), **_projects(now), **_orgs_and_skills(now)}.items():
        notebook.write(record, text)
    notebook.stub_person("people/quinn-alder.md", "Quinn Alder", handles=["quinn@alder.example"])
    notebook.stub_person("people/noor-bakhtiar.md", "Noor Bakhtiar", handles=["noor@bakhtiar.example"])
    # The map's correspondent rows: where the People table's mail columns come from.
    mail = [("mara@fernhill.example", "people/mara-ostrowski.md", 38, 21, 41, 1), ("tomas.reyes@mailbox.example", "people/tomas-reyes.md", 6, 4, 60, 3),
            ("ines@ledgerline.example", "people/ines-halvorsen.md", 9, 2, 30, 12), ("quinn@alder.example", "people/quinn-alder.md", 3, 2, 20, 15),
            ("noor@bakhtiar.example", "people/noor-bakhtiar.md", 2, 1, 50, 44)]
    rows = [{"address": address, "record": record, "name": record, "mails": sent + received, "sent": sent, "received": received,
             "first": _day(now, first), "last": _day(now, last), "one_way": False}
            for address, record, received, sent, first, last in mail]
    (root / ".state").mkdir(exist_ok=True)
    (root / ".state" / "map.json").write_text(json.dumps({"people": rows}))
    runs = root / ".state" / "runs"
    runs.mkdir(parents=True, exist_ok=True)
    for i, run in enumerate(_runs(now)):
        run["id"] = f"run_{i:032x}"
        (runs / f"{run['id']}.json").write_text(json.dumps(run))
    return root
