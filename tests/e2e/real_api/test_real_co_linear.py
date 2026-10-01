"""co linear against a real Linear workspace: every read, then create → comment → update on a test issue.

LLM-Note: Opt-in (real_api). Skips unless LINEAR_API_KEY is set in the shell, ~/.co/keys.env or the
`co env set --secret` store. Writes to the workspace: it creates one issue whose title says it is a
test, comments on it, and moves it to a completed state, so it does not sit in anyone's open list. Linear has no `co linear` delete, so the
closed issue stays; archive it in Linear if you want it gone.

    co env set LINEAR_API_KEY lin_api_... --secret   # once; or export LINEAR_API_KEY
    pytest -m real_api tests/e2e/real_api/test_real_co_linear.py -s
    LINEAR_TEST_TEAM=ENG  # optional: the team to create in; default is the first team listed
"""

import json
import os
import re
import time

import pytest
from typer.testing import CliRunner

from connectonion.cli.main import app
from connectonion.environment import setting

# The key is found where the command finds it: the shell, ~/.co/keys.env, or the
# store `co env set LINEAR_API_KEY ... --secret` writes. os.environ alone never
# sees the last one, and the test skipped with the key right there.
pytestmark = pytest.mark.skipif(not setting("LINEAR_API_KEY"), reason="LINEAR_API_KEY not set (co env set LINEAR_API_KEY lin_api_... --secret)")


def co(*args):
    result = CliRunner().invoke(app, ["linear", *args])
    assert result.exit_code == 0, f"co linear {' '.join(args)} exited {result.exit_code}:\n{result.output}"
    return result


def as_json(*args):
    return json.loads(co(*args, "--json").stdout)


def test_reads_then_create_comment_update_on_a_test_issue():
    assert "Acting as" in co("check").stdout
    teams = as_json("teams")
    team = os.getenv("LINEAR_TEST_TEAM") or teams[0]["key"]
    states = as_json("states", "--team", team)
    for listing in (["labels", "--team", team], ["users"], ["projects"], ["issues", "--mine"],
                    ["issues", "--team", team, "--state", states[0]["name"], "-n", "5"], ["search", "bug", "-n", "5"]):
        assert isinstance(as_json(*listing), list)

    title = f"[co linear real_api test] safe to close {int(time.time())}"
    preview = co("create", title, "--team", team, "--assignee", "me", "--priority", "low")
    assert "Preview" in preview.stdout

    created = co("create", title, "--team", team, "--assignee", "me", "--priority", "low",
                 "--description", "Created by tests/e2e/real_api/test_real_co_linear.py", "--yes")
    identifier = re.search(r"Created (\S+):", created.stdout)[1]
    issue = as_json("issue", identifier)
    assert issue["title"] == title and issue["priority"] == "Low"

    co("comment", identifier, "Comment from the co linear real_api test.", "--yes")
    assert [c["body"] for c in as_json("issue", identifier)["comments"]] == ["Comment from the co linear real_api test."]

    finished = next(s["name"] for s in states if s["type"] in ("completed", "canceled"))
    co("update", identifier, "--state", finished, "--priority", "none", "--yes")
    issue = as_json("issue", identifier)
    assert issue["state"] == finished and issue["priority"] == "No priority"
