"""co canny against a real Canny account (#2050). Opt-in.

    CANNY_API_KEY=... pytest -m real_api tests/e2e/real_api/test_real_co_canny.py

Reads only, unless CANNY_TEST_BOARD names a board (id or exact name) that may
be written to; then it also needs CANNY_USER_ID (an admin's Canny user id, from
`co canny check --email`). The writes are: a comment marked internal, and a
status change of that board's newest post to the status it already has, which
Canny records as nothing and emails no one. It creates no changelog entry,
because Canny has no API to delete one.
"""

import json
import os

import pytest
from typer.testing import CliRunner

from connectonion.cli.main import app

pytestmark = [pytest.mark.real_api,
              pytest.mark.skipif(not os.environ.get("CANNY_API_KEY"), reason="CANNY_API_KEY not set")]
writes = pytest.mark.skipif(not (os.environ.get("CANNY_TEST_BOARD") and os.environ.get("CANNY_USER_ID")),
                            reason="CANNY_TEST_BOARD and CANNY_USER_ID not both set")


def canny(*args, input=None):
    result = CliRunner().invoke(app, ["canny", *args], input=input)
    assert result.exit_code == 0, result.output
    return result


def test_check_sees_boards():
    assert "Boards:" in canny("check").output


def test_boards_json():
    boards = json.loads(canny("boards", "--json").stdout)["boards"]
    assert all({"id", "name", "posts"} <= set(b) for b in boards)


def test_top_voted_open_posts_then_one_post():
    posts = json.loads(canny("posts", "--status", "open", "--sort", "score", "-n", "5", "--json").stdout)["posts"]
    assert len(posts) <= 5
    assert [p["votes"] for p in posts] == sorted((p["votes"] for p in posts), reverse=True)
    if posts:
        detail = json.loads(canny("post", posts[0]["id"], "--json").stdout)
        assert detail["id"] == posts[0]["id"] and "comments" in detail


def test_search_and_changelog_read():
    json.loads(canny("search", "the", "-n", "3", "--json").stdout)
    json.loads(canny("changelog", "-n", "3", "--json").stdout)


def _newest_post_on_test_board():
    posts = json.loads(canny("posts", "--board", os.environ["CANNY_TEST_BOARD"], "-n", "1", "--json").stdout)["posts"]
    if not posts:
        pytest.skip("CANNY_TEST_BOARD has no posts to write to")
    return posts[0]


@writes
def test_internal_comment_on_the_test_board():
    post = _newest_post_on_test_board()
    assert "Nothing changed" in canny("comment", post["id"], "co canny real_api test", "--internal").output
    assert "Commented on" in canny("comment", post["id"], "co canny real_api test", "--internal", "--yes").output


@writes
def test_status_change_to_the_same_status_is_accepted():
    post = _newest_post_on_test_board()
    assert "Canny will record nothing" in canny("status", post["id"], post["status"]).output
    assert "Changed" in canny("status", post["id"], post["status"], "--yes").output
