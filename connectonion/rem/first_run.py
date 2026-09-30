"""What the first run will write and spend, said once before anything is spent (#2008).

1.9.0a5 announced "~90k billed input per project page, about a minute" and
measured 614k and 922k, four to five minutes each, with every project active
in the window queued and no total. The first run is now capped (FIRST_PEOPLE,
FIRST_PROJECTS; init's --first-people / --first-projects raise it), and its
cost is one sum stated before the first page: pages x the median of this
notebook's own completed runs of that kind, or, before there are any, the
defaults below. Either way it is an estimate, and the line says so.
"""

from statistics import median

FIRST_PEOPLE = 3
FIRST_PROJECTS = 3

# Measured on the owner's real notebook, 2026-10-01 (#2008): your page 678k
# billed input in 6m17s; project pages 614k and 922k, 4-5 minutes each;
# people 150k-700k (one stopped by hand at 1.93M). The middle of each range.
DEFAULTS = {"owner": {"input_tokens": 680_000, "seconds": 380},
            "person": {"input_tokens": 425_000, "seconds": 300},
            "project": {"input_tokens": 750_000, "seconds": 270}}

# Which run records are which kind of page: `_logged`'s phase, and the record's folder.
_PHASES = {"owner": ("investigate me", ""), "person": ("investigate", "people/"),
           "project": ("projects write", "projects/")}


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


def plan(runs: list[dict], *, owner: bool, people: int, projects: int) -> dict:
    """The whole first run's pages, billed input and minutes, from `per_page`."""
    counts = {"owner": int(owner), "person": people, "project": projects}
    rates = {kind: per_page(runs, kind) for kind in counts}
    return {"pages": sum(counts.values()), "counts": counts,
            "input_tokens": sum(counts[k] * rates[k]["input_tokens"] for k in counts),
            "minutes": round(sum(counts[k] * rates[k]["seconds"] for k in counts) / 60),
            "measured": {k: rates[k]["measured"] for k in counts if counts[k]}}


def tokens(number: int) -> str:
    return f"{number / 1e6:.1f}M" if number >= 1_000_000 else f"{round(number / 1000)}k"


def _pages(counts: dict) -> str:
    parts = (["your page"] if counts["owner"] else []) + [
        f"{counts[kind]} {word if counts[kind] == 1 else plural}"
        for kind, word, plural in (("person", "person", "people"), ("project", "project", "projects"))
        if counts[kind]]
    return ", ".join(parts[:-1]) + " and " + parts[-1] if len(parts) > 1 else parts[0] if parts else "nothing"


def announce(total: dict, where: str) -> str:
    """The one line said before the first page: pages, billed input, minutes, and how it was estimated."""
    measured = total["measured"]
    basis = ("from this notebook's own runs" if measured and all(measured.values()) else
             "from runs measured on a real notebook" if not any(measured.values()) else
             "from this notebook's runs where it has them, measured defaults otherwise")
    return (f"About {total['pages']} page{'s' if total['pages'] != 1 else ''} ({_pages(total['counts'])}), "
            f"~{tokens(total['input_tokens'])} billed input tokens {where}, ~{total['minutes']} minutes "
            f"(an estimate {basis}).")
