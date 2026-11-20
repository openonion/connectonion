"""An invented notebook big enough to judge the Knowledge graph honestly (#3085).

A designer refused the graph on a real notebook of about 200 marks; a fixture of four pages hides every
problem she named (no key, cut labels, labels on marks, marks too small to tap). This one has 110 people,
24 organisations, 32 projects, 6 decisions and 5 knowledge entries, all linked, with titles as long as real
ones and one entry translated into Chinese. Every name is made up; the same call always builds the same notebook.
"""

import random
from datetime import datetime, timezone

from connectonion.rem.config import prepare
from connectonion.rem.files import Notebook

FIRST = ["Mara", "Quinn", "Ellis", "Inès", "Tobiah", "Lucinda", "Odalys", "Bram", "Sorrel", "Hespera", "Calder",
         "Wren", "Ignace", "Petra", "Lior", "Anouk", "Dashiell", "Marisol", "Thaddeus", "Yseult", "Corwin", "Nell"]
LAST = ["Ostrowski", "Alder", "Park", "Halvorsen", "Quillfeather", "Marchetti-Bell", "Venn", "Okonjo", "Thistlewood", "Ravensworth"]
ORGS = ["Fernhill Labs", "Cove Dairy Collective", "Harbour Pilots' Guild of the Northern Sound", "Lantern Glassworks",
        "Kiln Cooperative", "Tidewater Survey", "Barley & Rye Mutual", "Seed Library of the Three Valleys", "Wool Board",
        "Saltmarsh Trust", "Greywater Engineering", "Orchard Row Press", "Quarry Lane Studio", "Northlight Freight",
        "Hollow Oak Farm", "Petrel Instruments", "Mossbank Council", "Juniper Street Clinic", "Copperline Rail",
        "Ashgrove School", "Foxglove Bakery", "Stonecrop Insurance", "Heron Point Marina", "Larkspur Radio"]
PROJECTS = ["Cove", "Barn retrofit for the upper valley dairies", "Tide tables", "Harbour permit renewal", "Lantern relight",
            "Kiln rebuild", "Seed catalogue", "Wool grading pilot", "Saltmarsh survey", "Greywater loop", "Orchard almanac",
            "Quarry open day", "Freight timetable", "Hollow Oak cold store", "Petrel calibration", "Mossbank footbridge",
            "Clinic rota", "Copperline crossing", "Ashgrove greenhouse", "Foxglove ovens", "Stonecrop claim", "Marina dredge",
            "Larkspur winter schedule", "Thermal battery field trial", "Glass sourcing", "Pilot handbook", "Lending ledger",
            "Fleece auction", "Reed bed", "Signal mast", "Ferry subsidy", "Night market"]
# (file, title, also known as, Chinese title when the fixture translates it, how many records it ties together)
KNOWLEDGE = [
    ("heat-storage", "Heat storage for off-grid dairy barns in cold valleys", ["Heat storage", "thermal battery"], "寒冷山谷里离网奶牛棚的储热", 26),
    ("tide-forecasting", "Tide-table forecasting for small harbour pilots", ["Tide tables"], "", 19),
    ("seed-lending", "Seed-library lending rules and what a late return costs", ["Seed lending"], "", 14),
    ("lantern-glass", "Lantern glass sourcing after the kiln cooperative closed", ["Lantern glass"], "", 11),
    ("wool-grading", "Wool grading", ["Fleece grades"], "", 7),
]
DECISIONS = ["Buy the second thermal battery", "Keep the tide tables on paper", "Charge nothing for a late seed return",
             "Order glass from two kilns", "Grade fleece by hand this season", "Close the night market in January"]


def slug(name: str) -> str:
    return "".join(ch if ch.isalnum() else "-" for ch in name.lower().replace("è", "e")).strip("-").replace("--", "-")


def people_names() -> list[str]:
    return [f"{first} {LAST[(i + j) % len(LAST)]}" for j in range(5) for i, first in enumerate(FIRST)]


def link(folder: str, name: str, here: str) -> str:
    return f"[{name}]({'' if here == folder else '../' + folder + '/'}{slug(name)}.md)"


def _write_people(nb, rng, names):
    for i, name in enumerate(names):
        org = ORGS[i % len(ORGS)] if i % 7 else ORGS[rng.randrange(4)]
        role = rng.choice(["Farm engineer", "Harbour pilot", "Glassblower", "Seed librarian", "Wool grader", "Surveyor"])
        nb.write(f"people/{slug(name)}.md", f"# {name}\n\n{name} is a {role.lower()} at {link('orgs', org, 'people')} [1].\n\n"
                 f"## Facts\n- Role: {role}\n- Company: {link('orgs', org, 'people')} [1]\n\n"
                 f"## Sources\n- [1] gmail:p{i} — 2026-09-{1 + i % 28:02d} — {name}\n")


def _write_orgs(nb):
    for i, org in enumerate(ORGS):
        nb.write(f"orgs/{slug(org)}.md", f"# {org}\n\n{org} works with the user on the valley's projects [1].\n\n"
                 f"## Sources\n- [1] gmail:o{i} — 2026-08-{1 + i % 28:02d} — {org}\n")


def _write_projects(nb, rng, names):
    for i, project in enumerate(PROJECTS):
        crew = rng.sample(names, 2 + (i * 5) % 7 + (9 if i < 3 else 0))
        lines = [f"- {link('people', name, 'projects')} works on {project} [1]." for name in crew]
        lines += [f"- {link('orgs', ORGS[(i + k) % len(ORGS)], 'projects')} pays for part of it [1]." for k in range(1 + i % 2)]
        nb.write(f"projects/{slug(project)}.md", f"# {project}\n\n## What it is\n- {project} is one of the valley's shared works [1].\n\n"
                 f"## People and ownership\n" + "\n".join(lines) + f"\n\n## Sources\n- [1] gmail:j{i} — 2026-09-{1 + i % 28:02d} — {project}\n")


def _write_knowledge(nb, rng, names):
    for file, title, aliases, zh, size in KNOWLEDGE:
        people = rng.sample(names, size * 3 // 5)
        projects = rng.sample(PROJECTS, size - len(people) - 2)
        orgs = rng.sample(ORGS, 2)
        nb.write(f"knowledge/{file}.md", f"# {title}\n\n- Also known as: {'; '.join(aliases)}\n\n"
                 f"## What it is\n- {title} is what the valley learned the slow way [1].\n\n## People\n"
                 + "\n".join(f"- {link('people', name, 'knowledge')} knows {aliases[0].lower()} first-hand [1]." for name in people)
                 + "\n\n## Orgs\n" + "\n".join(f"- {link('orgs', org, 'knowledge')} keeps the records [1]." for org in orgs)
                 + "\n\n## Projects\n" + "\n".join(f"- {link('projects', project, 'knowledge')} depends on it [1]." for project in projects)
                 + f"\n\n## Sources\n- [1] gmail:k-{file} — 2026-09-20 — {aliases[0]}\n")
        if zh:
            _translate(nb, f"knowledge/{file}.md", title, zh)


def _translate(nb, record: str, title: str, zh: str):
    """A current Chinese translation, saved the way `co rem translate` saves one."""
    from connectonion.rem.translate import digest, translation_path
    original = nb.read(record)
    path = translation_path(nb.root, record, "zh")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"<!-- co rem translation of {record} sha256:{digest(original)} -->\n" + original.replace(f"# {title}", f"# {zh}", 1), encoding="utf-8")


def _write_decisions(nb):
    for i, decision in enumerate(DECISIONS):
        nb.write(f"decisions/{slug(decision)}.md", f"# {decision}\n\n- Decided for {link('projects', PROJECTS[i * 5], 'decisions')} [1].\n\n"
                 f"## Sources\n- [1] gmail:d{i} — 2026-09-1{i} — {decision}\n")


def build(root, now: datetime = datetime(2026, 10, 1, 12, tzinfo=timezone.utc)):
    """Write the notebook under `root` and return it. `now` is unused by the pages; it keeps the signature of the other fixture."""
    prepare(root)
    nb, rng, names = Notebook(root), random.Random(3085), people_names()
    _write_people(nb, rng, names)
    _write_orgs(nb)
    _write_projects(nb, rng, names)
    _write_knowledge(nb, rng, names)
    _write_decisions(nb)
    # Two pages nothing links to: the key says so in words instead of drawing them.
    nb.write("people/ellis-nobody.md", "# Ellis Nobody\n\nEllis once said heat storage at a dinner.\n")
    nb.write("principles/steady.md", "# Steady pace\n\nKeep a steady pace.\n")
    return root
