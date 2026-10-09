"""Estimate the first run's selected investigations before they start (#2008).

1.9.0a5 announced "~90k billed input per project page, about a minute" and
measured 614k and 922k, four to five minutes each, with every project active
in the window queued and no total. The first run now selects all eligible people,
projects and organizations (init's --first-* flags cap each kind), and its
cost is one sum stated before the first page: pages x the median of this
notebook's own completed runs of that kind, or, before there are any, the
defaults below. Either way it is an estimate, and the line says so.
"""

from itertools import zip_longest
from math import ceil
from statistics import median

FIRST_PEOPLE = None    # None: every eligible page of the kind; init's flags cap it
FIRST_PROJECTS = None
FIRST_ORGS = None
WORKERS = 48           # pages investigated at once after the owner's page

# Planning rates from the 2026-10-03 90-day concurrent first-run sample and
# separate full Person/Skill reads. The sample was interrupted; these rates
# estimate completed pages, not the cost of all retries or refusals. An owner's
# first page takes two turns: quick and full. Completed notebook-local runs
# replace these defaults as soon as they exist.
DEFAULTS = {"owner": {"input_tokens": 1_160_000, "seconds": 416},
            "person": {"input_tokens": 1_100_000, "seconds": 290},
            "project": {"input_tokens": 1_200_000, "seconds": 250},
            "org": {"input_tokens": 120_000, "seconds": 90},
            "skill": {"input_tokens": 500_000, "seconds": 180}}

# Which run records are which kind of page: `_logged`'s phase, and the record's folder.
_PHASES = {"owner": ("investigate me", ""), "person": ("investigate", "people/"),
           "project": ("projects write", "projects/"), "org": ("investigate", "orgs/"),
           "skill": ("investigate", "skills/catalog/")}


def per_page(runs: list[dict], kind: str) -> dict:
    """The median billed input and duration of this notebook's completed pages of `kind`.

    Only completed runs that reported usage count: a run stopped by hand or
    without a meter says nothing about what a whole page costs.
    """
    phase, folder = _PHASES[kind]
    done = [run for run in runs
            if run.get("phase") == phase and run.get("outcome") == "completed"
            and str(run.get("record", "")).startswith(folder)
            and isinstance((run.get("usage") or {}).get("input_tokens"), int)]
    if not done:
        return {**DEFAULTS[kind], "measured": 0}
    seconds = [run["seconds"] for run in done if isinstance(run.get("seconds"), (int, float))]
    return {"input_tokens": int(median(run["usage"]["input_tokens"] for run in done)),
            "seconds": int(median(seconds)) if seconds else DEFAULTS[kind]["seconds"],
            "measured": len(done)}


def plan(runs: list[dict], *, owner: bool, people: int, projects: int, orgs: int = 0, skills: int = 0,
         workers: int = WORKERS) -> dict:
    """Selected pages, billed input and wall-clock minutes from observed medians.

    The owner's quick turn runs alone, then its full turn shares workers with
    interleaved people, projects and organizations. Simulate that queue; dividing
    total work by worker count misses the last slow page in a batch.
    """
    counts = {"owner": int(owner), "person": people, "project": projects, "org": orgs}
    if skills:
        counts["skill"] = skills
    rates = {kind: per_page(runs, kind) for kind in counts}
    queue = ([rates["owner"]["seconds"]] if owner else []) + [
        seconds for group in zip_longest(*(
            [rates[kind]["seconds"]] * counts[kind] for kind in counts if kind != "owner"))
        for seconds in group if seconds is not None]
    lanes = [0] * max(workers, 1)
    for seconds in queue:
        lane = min(range(len(lanes)), key=lanes.__getitem__)
        lanes[lane] += seconds
    return {"pages": sum(counts.values()), "counts": counts,
            "input_tokens": (2 * counts["owner"] * rates["owner"]["input_tokens"]
                             + sum(counts[k] * rates[k]["input_tokens"] for k in counts if k != "owner")),
            "minutes": ceil((counts["owner"] * rates["owner"]["seconds"] + max(lanes)) / 60),
            "measured": {k: rates[k]["measured"] for k in counts if counts[k]}}


def tokens(number: int) -> str:
    return f"{number / 1e6:.1f}M" if number >= 1_000_000 else f"{round(number / 1000)}k"


def _pages(counts: dict) -> str:
    parts = (["your page"] if counts["owner"] else []) + [
        f"{counts[kind]} {word if counts[kind] == 1 else plural}"
        for kind, word, plural in (("person", "person", "people"), ("project", "project", "projects"),
                                   ("org", "organisation", "organisations"), ("skill", "skill", "skills"))
        if counts.get(kind)]
    return ", ".join(parts[:-1]) + " and " + parts[-1] if len(parts) > 1 else parts[0] if parts else "nothing"


def announce(total: dict, where: str) -> str:
    """The one line said before the first page: pages, billed input, minutes, and how it was estimated."""
    measured = total["measured"]
    basis = ("from this notebook's own runs" if measured and all(measured.values()) else
             "from runs measured on a real notebook" if not any(measured.values()) else
             "from this notebook's runs where it has them, measured defaults otherwise")
    if total['counts'].get('skill') and not measured.get('skill'):
        basis += "; skill time and tokens are planning estimates from sampled runs"
    return (f"About {total['pages']} page{'s' if total['pages'] != 1 else ''} ({_pages(total['counts'])}), "
            f"~{tokens(total['input_tokens'])} billed input tokens {where}, ~{total['minutes']} minutes "
            f"(an estimate {basis}).")
