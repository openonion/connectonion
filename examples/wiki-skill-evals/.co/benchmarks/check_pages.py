"""Check what the eval judge cannot see: the whole page on disk.

`co eval` shows its judge the first 4,000 characters of the answer, and a
project page runs past that, so the judge could not see `Paths` or the last
headings. This reads each out/<case>.md the Agent wrote and checks the page
contract with the Wiki's own validator plus the mapped lines a page must keep.

    python .co/benchmarks/check_pages.py   # after co eval run; exit 1 on any problem

It lives under .co/benchmarks/ because `co eval run` keeps that folder from
the Agent under test: a run once found this checker and ran it on itself.
"""

import re
import sys
from pathlib import Path

from connectonion.wiki.page_review import normalize_numbered_sources, restore_runner_fields, validate

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
    record = ("people/" if case.stem.startswith(("person-", "people-")) else "projects/") + case.stem + ".md"
    if (fixture / "evidence").is_dir():
        # wiki-person-search (#1943): the ids are the first lines of the evidence files, as in production.
        texts = [path.read_text() for path in (fixture / "evidence").rglob("*.md")]
        items = [{"source": source} for text in texts for source in re.findall(r"^### (\S+:\S+) · ", text, re.M)]
    else:
        items = [{"source": source} for source in
                 re.findall(r"^### (\S+:\S+:\d+) ", (fixture / "material.md").read_text(), re.M)]
    items += [{"source": "notebook:owner"}, {"source": "investigation:coverage"}]
    candidate = restore_runner_fields(record, normalize_numbered_sources(page), original)
    found = validate(record, candidate, original, items)
    kept = [line for line in original.splitlines() if line.startswith("- Email:") and line not in candidate]
    # A string the page must never carry (a secret), anywhere in it: the judge
    # sees only the first 4,000 characters, so it cannot say.
    forbidden = fixture / "forbidden.txt"
    leaked = [s for s in (forbidden.read_text().split("\n") if forbidden.is_file() else []) if s and s in page]
    return found + [f"lost mapped line: {line}" for line in kept] + [f"forbidden text on the page: {s[:12]}…" for s in leaked]


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
