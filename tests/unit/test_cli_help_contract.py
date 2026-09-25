"""Every `co` command's help meets the #1643 contract, judged the way an agent meets it (#1657, #1735).

This runs `co audit`'s engine for real: it starts `co --help`, follows every
command the pages list, and checks each printed page. Nothing here reads the
source, so a label that lives in a docstring but never prints does not pass.

`co wiki` prints reviewed pages word for word and is held to them by
tests/e2e/cli/test_wiki_help_contract.py.
"""

import pytest

from connectonion.cli import audit


@pytest.mark.timeout(900)
def test_every_page_meets_the_contract():
    findings, checked = audit.audit()
    assert len(checked) > 200, f"the walk reached only {len(checked)} pages"
    assert not findings, "\n".join(f"{f.path}  {f.check}: {f.fix}" for f in findings) + "\nRun: co audit"
