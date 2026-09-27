"""`co` passes `co audit co`, plus its own house style, judged from printed pages (#1657, #1721, #1735).

`co audit` holds every CLI to the same rules; this test runs that engine on
`co` itself. On top, three conventions that are ours rather than universal:
each page says what it changes in a fixed word, names its way back, and every
command `co commands` lists can be reached from `co --help`.

`co wiki` prints reviewed pages word for word and is held to them by
tests/e2e/cli/test_wiki_help_contract.py; it is being rewritten (#1667).
"""

import re

import pytest

from connectonion.cli import audit

LABELS = re.compile(r"\b(Read-only|Writes|Sends|Deletes|Removes|Creates|Changes|Charges|"
                    r"Deploys|Installs|Uploads|Publishes|Starts|Stops|Runs)\b")
OWN_PAGES = "co wiki"


@pytest.mark.timeout(900)
def test_co_meets_the_contract_and_its_house_style():
    findings, checked = audit.audit(["co"])
    ours = {path: page for path, page in checked.items() if not path.startswith(OWN_PAGES)}
    assert len(ours) > 200, f"the walk reached only {len(ours)} pages"
    problems = [f"{f.path}  {f.check}: {f.fix}" for f in findings if not f.path.startswith(OWN_PAGES)]
    problems += [f"{path}  side_effect: say what it changes with one of: {LABELS.pattern}"
                 for path, page in ours.items() if not LABELS.search(page.text)]
    problems += [f"{path}  back: no Back: line" for path, page in ours.items()
                 if path != "co" and not re.search(r"\b(Back|Next):", page.text)]
    listed = audit.run(["co", "commands"]).text
    registered = set(re.findall(r"^(co(?: [a-z][a-z0-9_-]*)*)(?:\s{2,}|$)", listed, re.M))
    problems += [f"{path}  unreachable: co commands lists it, no page from co --help does"
                 for path in sorted(registered - set(checked)) if not path.startswith(OWN_PAGES + " ")]
    assert not problems, "\n".join(problems) + "\nRun: co audit co"
