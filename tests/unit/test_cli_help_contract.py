"""`co` passes `co audit co`, plus its own house style, judged from printed pages (#1657, #1721, #1735).

`co audit` holds every CLI to the same rules; this test runs that engine on
`co` itself. On top, three conventions that are ours rather than universal:
each page says what it changes in a fixed word, names its way back, and every
command `co commands` lists can be reached from `co --help`.

`co rem` prints reviewed pages word for word and is held to them by
tests/e2e/cli/test_rem_help_contract.py; it is being rewritten (#1667).
It is held to the look rule (#1997) all the same, except for LOOK_PENDING.
"""

import re

import pytest

from connectonion.cli import audit

LABELS = re.compile(r"\b(Read-only|Writes|Sends|Deletes|Removes|Creates|Changes|Charges|"
                    r"Deploys|Installs|Uploads|Publishes|Starts|Stops|Runs)\b")
OWN_PAGES = "co rem"
# co rem pages that fail the look rule today: plain in a terminal, because
# rem_help.py prints them verbatim. Their rewrite onto connectonion/cli/style.py
# is #1996, and this set must shrink to empty when it lands. It can only
# shrink: a page here that passes (or is gone) fails the test until it is taken
# out, and nothing outside co rem may wait here.
LOOK_PENDING: set = set()


def look_problems(findings: list, pending: set = LOOK_PENDING) -> list:
    """co rem's look findings beyond the baseline, and baseline entries that no longer fail."""
    failing = {f.path for f in findings if f.check == "look"}
    problems = [f"{path}  look: only co rem may wait on #1996" for path in sorted(pending)
                if not path.startswith(OWN_PAGES)]
    problems += [f"{f.path}  look: {f.fix}" for f in findings
                 if f.check == "look" and f.path.startswith(OWN_PAGES) and f.path not in pending]
    problems += [f"{path}  look: passes now; take it out of LOOK_PENDING" for path in sorted(pending - failing)]
    return problems


def test_the_look_baseline_can_only_shrink():
    plain = audit.Finding("co rem list", "look", "help has no colour in a terminal")
    new = audit.Finding("co rem new", "look", "help has no colour in a terminal")
    assert look_problems([plain], {"co rem list"}) == []
    assert [p.split()[2] for p in look_problems([plain, new], {"co rem list"})] == ["new"]
    assert "passes now" in " ".join(look_problems([], {"co rem list"}))
    assert "only co rem" in " ".join(look_problems([plain], {"co rem list", "co gmail"}))


@pytest.mark.timeout(900)
def test_co_meets_the_contract_and_its_house_style():
    findings, checked = audit.audit(["co"])
    ours = {path: page for path, page in checked.items() if not path.startswith(OWN_PAGES)}
    assert len(ours) > 200, f"the walk reached only {len(ours)} pages"
    problems = [f"{f.path}  {f.check}: {f.fix}" for f in findings if not f.path.startswith(OWN_PAGES)]
    problems += look_problems(findings)
    problems += [f"{path}  side_effect: say what it changes with one of: {LABELS.pattern}"
                 for path, page in ours.items() if not LABELS.search(page.text)]
    problems += [f"{path}  back: no Back: line" for path, page in ours.items()
                 if path != "co" and not re.search(r"\b(Back|Next):", page.text)]
    listed = audit.run(["co", "commands"]).text
    registered = set(re.findall(r"^(co(?: [a-z][a-z0-9_-]*)*)(?:\s{2,}|$)", listed, re.M))
    problems += [f"{path}  unreachable: co commands lists it, no page from co --help does"
                 for path in sorted(registered - set(checked)) if not path.startswith(OWN_PAGES + " ")]
    assert not problems, "\n".join(problems) + "\nRun: co audit co"
