"""co notion against a real Notion workspace. Opt-in, and read-only like the commands.

    co env set NOTION_API_KEY ntn_... --secret                 # an internal connection's token (or a personal access token)
    export NOTION_TEST_PAGE=https://www.notion.so/...          # a page that key can read
    export NOTION_TEST_DATABASE=https://www.notion.so/...      # optional: a database that key can read
    pytest -m real_api tests/e2e/real_api/test_real_co_notion.py

The key is found the way `co notion` finds it, through environment.setting(): the shell,
~/.co/keys.env, then `co env set --secret`'s store. Nothing in Notion is changed.
"""

import json

import pytest
from typer.testing import CliRunner

from connectonion.cli.main import app
from connectonion.environment import load_environment, setting

load_environment()
pytestmark = [pytest.mark.real_api,
              pytest.mark.skipif(not (setting("NOTION_API_KEY") and setting("NOTION_TEST_PAGE")),
                                 reason="NOTION_API_KEY or NOTION_TEST_PAGE is set nowhere")]
database = pytest.mark.skipif(not setting("NOTION_TEST_DATABASE"), reason="NOTION_TEST_DATABASE not set")


def notion(*args):
    result = CliRunner().invoke(app, ["notion", *args])
    assert result.exit_code == 0, f"co notion {' '.join(args)} exited {result.exit_code}:\n{result.output}"
    return result


def as_json(*args):
    return json.loads(notion(*args, "--json").stdout)


def test_check_reaches_the_test_page():
    assert "Target shared: page" in notion("check", "--target", setting("NOTION_TEST_PAGE")).stdout


def test_pages_lists_what_is_shared():
    listed = as_json("pages", "-n", "5")
    assert listed["results"] and "not a list of the whole workspace" in listed["note"]


def test_the_test_page_reads_with_its_coverage():
    page = as_json("page", setting("NOTION_TEST_PAGE"))
    assert page["url"].startswith("https://") and page["coverage"]["blocks"] >= 0
    assert isinstance(page["coverage"]["complete"], bool)


@database
def test_the_test_database_has_columns_and_rows():
    found = as_json("columns", setting("NOTION_TEST_DATABASE"))
    assert any(column["type"] == "title" for column in found["columns"])
    rows = as_json("db", setting("NOTION_TEST_DATABASE"), "-n", "3")
    assert "rows" in rows and rows["data_source"]["id"] == found["data_source"]["id"]
