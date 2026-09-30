"""Check what the eval judge cannot see: the whole page on disk.

`co eval` shows its judge the first 4,000 characters of the answer, and a
project page runs past that, so the judge could not see `Paths` or the last
headings. This reads each out/<case>.md the Agent wrote and checks the page
contract with co rem's own validator plus the mapped lines a page must keep.

    python .co/benchmarks/check_pages.py   # after co eval run; exit 1 on any problem

It lives under .co/benchmarks/ because `co eval run` keeps that folder from
the Agent under test: a run once found this checker and ran it on itself.
"""

import re
import sys
from pathlib import Path

from connectonion.rem.page_review import normalize_numbered_sources, restore_runner_fields, validate

HERE = Path(__file__).parents[2]  # .co/benchmarks/ -> the eval workspace
FIXTURES = Path(__file__).parent / "fixtures"


def problems(case: Path, page: str) -> list[str]:
    """The checks a real investigation's candidate meets before it is saved.

    Same order as the runner: accept a numbered-list Sources spelling, put back
    the lines the runner owns, then validate. The fixtures carry source ids in
    the production shape (gmail:<case>:1, codex:<case>:2), plus
    investigation:page and notebook:owner as a real run supplies them.
    """
    fixture = FIXTURES / case.stem
    original = (fixture / "page.md").read_text()
    record = ("people/" if case.stem.startswith("person-") else "projects/") + case.stem + ".md"
    items = [{"source": source} for source in re.findall(r"^### (\S+:\S+:\d+) ", (fixture / "material.md").read_text(), re.M)]
    items += [{"source": "notebook:owner"}, {"source": "investigation:coverage"}]
    candidate = restore_runner_fields(record, normalize_numbered_sources(page), original)
    found = validate(record, candidate, original, items)
    kept = [line for line in original.splitlines() if line.startswith("- Email:") and line not in candidate]
    # A string the page must never carry (a secret), anywhere in it: the judge
    # sees only the first 4,000 characters, so it cannot say.
    forbidden = fixture / "forbidden.txt"
    leaked = [s for s in (forbidden.read_text().split("\n") if forbidden.is_file() else []) if s and s in page]
    return (found + [f"lost mapped line: {line}" for line in kept]
            + [f"forbidden text on the page: {s[:12]}…" for s in leaked] + shape(record, page))


def section(page: str, heading: str) -> str:
    match = re.search(rf"(?ms)^## {re.escape(heading)}[ \t]*\n(.*?)(?=^## |^Investigation:|\Z)", page)
    return match.group(1) if match else ""


# #1974: what a reader sees first, and filler the judge might let through.
COVERAGE = re.compile(r"web: not searched|runs are offline|\bweb\b[^.\n]{0,40}\bnot searched", re.I)
HEDGE = re.compile(r"\b(?:do|does|did)(?: not|n't) (?:say|show|confirm|state|record|mention|report)\b"
                   r"|\bnot (?:confirmed|verified|recorded|stated|reported)\b|\bunconfirmed\b|\bunverified\b"
                   r"|\bno later message\b|\bwhether (?:it|this|that|they|these|the \w+) (?:was|were|is|are) "
                   r"(?:done|built|implemented|carried out|completed|shipped|delivered)\b", re.I)
MAX_HEDGES, MAX_STANDS = 3, 5
QUOTED = re.compile(r"“[^”]*”|\"[^\"\n]*\"|「[^」]*」|‘[^’]*’|`[^`\n]*`")
CJK = re.compile(r"[㐀-鿿]")


def shape(record: str, page: str) -> list[str]:
    """The page-shape rules of #1974 that a count can check without a judge."""
    found = [f"coverage filler on the page: {m[0]!r}" for m in COVERAGE.finditer(page)]
    if record.startswith("people/"):
        # The lead: prose between the title and `## Contact`, 2–3 sentences, ending in a last-contact date.
        lead = re.search(r"(?ms)\A# [^\n]*\n(.*?)^## Contact", page)
        text = lead.group(1).strip() if lead else ""
        if not text or text.startswith("Unknown — not investigated yet"):
            found.append("no lead before Contact")
        elif not re.search(r"Last contact:\s*(?:\d{4}-\d{2}-\d{2}|Unknown)", text):
            found.append("the lead gives no 'Last contact: <date>'")
        elif len([l for l in text.splitlines() if l.strip()]) > 3 or len(text) > 700:
            found.append(f"the lead is not short: {len(text)} characters")
    if record.startswith("projects/"):
        stands = [l for l in section(page, "Where it stands").splitlines() if re.match(r"\s*[-*] ", l)]
        if len(stands) > MAX_STANDS:
            found.append(f"Where it stands has {len(stands)} bullets (at most {MAX_STANDS})")
        body = re.split(r"(?m)^## Uncertainties", page)[0]
        hedges = HEDGE.findall(body)
        if len(hedges) > MAX_HEDGES:
            found.append(f"{len(hedges)} hedges above Uncertainties (at most {MAX_HEDGES}): {hedges[:4]}")
        # One language: English, a short quote may keep its own script.
        prose = QUOTED.sub("", re.split(r"(?m)^## Sources", page)[0])
        if len(CJK.findall(prose)) > 12:
            found.append(f"{len(CJK.findall(prose))} CJK characters outside quotes on an English page")
    return found


def main() -> int:
    failed = 0
    # agent.py moves each case's page here before the next case starts; the
    # last case's page is still in out/.
    pages = {p.name: p for p in (Path(__file__).parent / "written").glob("*.md")}
    pages.update({p.name: p for p in (HERE / "out").glob("*.md")})
    for case in (pages[name] for name in sorted(pages)):
        found = problems(case, case.read_text())
        failed += bool(found)
        print(("FAIL " if found else "PASS ") + case.stem + "".join(f"\n     {p}" for p in found))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
