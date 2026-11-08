"""An invented university with branches, teams and people, on top of the reader notebook.

Everything here is fictional (Fernhill University, its course teams, Fern, Rowan,
Juno…). The pages are written in the notebook's own grammar, so the real snapshot
derives Parent/Unit structure, rollups and obligations exactly as it would for
a real notebook; nothing about the organisation page is hand-placed.
"""

from datetime import datetime, timedelta
from pathlib import Path

from connectonion.rem.files import Notebook
from rem_reader_notebook import build as build_reader

UNIVERSITY = "orgs/fernhill-university.md"


def _day(now: datetime, days_ago: int) -> str:
    return (now - timedelta(days=days_ago)).strftime("%Y-%m-%d")


def _unit(title: str, kind: str, parent: str, you_are: str = "", history: str = "") -> str:
    you = f"- You are: {you_are} [1]\n" if you_are else ""
    return (f"# {title}\n\n## Facts\n- Kind: {kind} [1]\n- Parent: [{Path(parent).stem}]({Path(parent).name}) [1]\n{you}"
            f"{history}\n## Sources\n- [1] gmail:fixture-structure-{Path(title).stem.lower().replace(' ', '-')} — structure; observed 2026-08-01.\n")


def _person(name: str, unit: str, role: str, threads: list[str], history: list[str]) -> str:
    unit_name = Path(unit).name
    lines = "\n".join(f"- {line} [2]" for line in threads)
    past = "\n".join(f"- {line} [2]" for line in history)
    return (f"# {name}\n\n## Facts\n- Company: [Fernhill University](../orgs/fernhill-university.md) [1]\n"
            f"- Unit: [{Path(unit).stem}](../orgs/{unit_name}) [1]\n- Role in unit: [{Path(unit).stem}](../orgs/{unit_name}) — {role} [1]\n"
            f"- Role: {role} [1]\n\n## History\n{past or 'Unknown'}\n\n## Open threads\n{lines or 'Nothing open.'}\n\n"
            f"## Sources\n- [1] gmail:fixture-signature-{name.split()[0].lower()} — signature; observed 2026-08-01.\n"
            f"- [2] gmail:fixture-thread-{name.split()[0].lower()} — thread; observed 2026-09-20.\n")


def pages(now: datetime) -> dict:
    d = lambda n: _day(now, n)  # noqa: E731
    course, founders, office = "orgs/capstone-course.md", "orgs/founders-programme.md", "orgs/global-office.md"
    team = lambda code: f"orgs/team-{code.lower()}.md"  # noqa: E731
    result = {
        UNIVERSITY: f"""# Fernhill University

A public university; the user is a client of its capstone course and an incubatee of its founders programme [1].

## Facts
- Kind: university [1]
- To you: your capstone client, and the programme that incubates you [1]
- What they do: Teaching and research university [1]
- Website: https://fernhill-university.example [1]

## Domains
- fernhill-university.example [1]

## History
- {d(345)}: You first joined the capstone course as a client [1].
- {d(220)}: The founders programme accepted the user [1].
- {d(84)}: The global office proposed a summer internship [1].
- {d(9)}: Basil Thorne confirmed the final demo week [1].

## Sources
- [1] gmail:fixture-university — introductions; observed {d(9)}.
""",
        course: _unit("Capstone course", "course", UNIVERSITY, "client"),
        founders: _unit("Founders programme", "programme", UNIVERSITY, "incubatee"),
        office: _unit("Global office", "department", UNIVERSITY, "partner"),
        "orgs/accelerator-cohort.md": _unit("Accelerator cohort", "programme", founders),
        "orgs/maker-space.md": _unit("Maker space", "venue", founders),
        "orgs/summer-internship.md": _unit("Summer internship", "programme", office),
    }
    for code in ("T11A-KESTREL", "T12B-HERON", "T13C-WREN", "W14D-OSPREY", "T15E-FINCH", "T16F-LARK"):
        result[team(code)] = _unit(code, "team", course)
    people = [
        ("Fern Okafor", team("T11A-KESTREL"), "Product Owner",
         [f"The user owes Fern: Sprint 1 demo feedback — the user wrote “I'll watch the demo and send feedback that week”; since {d(30)}; due {d(14)}",
          f"Fern owes the user: the review questions in the backlog; since {d(37)}"],
         [f"{d(30)}: You promised feedback on the Sprint 1 demo"]),
        ("Rowan Pike", team("T12B-HERON"), "Scrum Master",
         [f"The user owes Rowan: written feedback on Demo A; since {d(22)}",
          f"The user owes Rowan: tell the team the Windows fix is on main, which blocks their testing; since {d(20)}"],
         [f"{d(22)}: Rowan sent the Demo A recording"]),
        ("Juno Hale", team("T13C-WREN"), "Product Owner",
         [f"The user owes Juno: whether the client meeting is weekly or fortnightly; since {d(33)}"],
         [f"{d(33)}: Juno asked about the meeting cadence a second time"]),
        ("Ilse Marr", team("W14D-OSPREY"), "Developer",
         [f"The user owes Ilse: credits for the new test agent address; since {d(37)}"], []),
        ("Theo Brand", team("W14D-OSPREY"), "Developer", [], []),
        ("Wren Ashby", team("T15E-FINCH"), "Product Owner",
         [f"Wren owes the user: the discovery report; since {d(37)}"], []),
        ("Cass Moreno", team("T16F-LARK"), "Product Owner", [], []),
        ("Basil Thorne", course, "Course convenor", [], [f"{d(9)}: Basil confirmed the final demo week"]),
        ("Nina Vale", "orgs/accelerator-cohort.md", "Programme lead", [], []),
        ("Tess Rowe", "orgs/maker-space.md", "Space manager",
         [f"Tess owes the user: the new access card; since {d(45)}"], []),
        ("Odile Grant", "orgs/summer-internship.md", "Internship coordinator", [], [f"{d(103)}: Odile sent the internship template"]),
    ]
    for name, unit, role, threads, history in people:
        result[f"people/{name.lower().replace(' ', '-')}.md"] = _person(name, unit, role, threads, history)
    result["people/petra-lund.md"] = (
        "# Petra Lund\n\n## Facts\n- Company: [Fernhill University](../orgs/fernhill-university.md) [1]\n\n"
        "## Sources\n- [1] gmail:fixture-signature-petra — signature; observed 2026-08-01.\n")
    return result


def build(root: Path, now: datetime) -> Path:
    """The reader notebook plus Fernhill University and its structure."""
    build_reader(root, now)
    notebook = Notebook(root)
    for record, text in pages(now).items():
        notebook.write(record, text)
    return root
