"""co canny against a fake Canny (httpx.MockTransport): every command, previews, failures (#2050).

The fake answers each endpoint with the shapes from Canny's API reference and
records every request, so a test can assert both what was printed and what
would have reached Canny.
"""

import json
from pathlib import Path

import httpx
import pytest
from typer.testing import CliRunner

from connectonion.cli.commands import canny_commands
from connectonion.cli.main import app

BOARD = {"id": "6a2889c586d7b8843bf4cf01", "name": "Feature Requests", "postCount": 123, "isPrivate": False,
         "created": "2026-01-02T00:00:00.000Z", "url": "https://acme.canny.io/admin/board/feature-requests"}
POST = {"id": "6a2889c586d7b8843bf4cf05", "title": "Dark mode [beta]", "status": "open", "score": 72,
        "board": BOARD, "created": "2026-09-30T10:00:00.000Z", "commentCount": 1, "details": "Please.",
        "author": {"name": "Sally Doe"}, "owner": None, "eta": None,
        "url": "https://acme.canny.io/admin/board/feature-requests/p/dark-mode"}
COMMENT = {"id": "6a2889c586d7b8843bf4cf0c", "author": {"name": "Sam Admin"}, "created": "2026-09-30T11:00:00.000Z",
           "internal": True, "value": "Looking at it"}
ENTRY = {"id": "6a2889c586d7b8843bf4cf08", "title": "Faster search", "status": "published", "types": ["improved"],
         "created": "2026-09-01T00:00:00.000Z", "publishedAt": "2026-09-02T00:00:00.000Z",
         "url": "https://acme.canny.io/changelog/faster-search"}
ADMIN = {"id": "6a2889c586d7b8843bf4cf07", "name": "Sam Admin", "isAdmin": True}

ANSWERS = {
    "v1/boards/list": {"boards": [BOARD]},
    "v1/posts/list": {"posts": [POST], "hasMore": True},
    "v1/posts/retrieve": POST,
    "v2/comments/list": {"items": [COMMENT], "hasNextPage": False},
    "v1/entries/list": {"entries": [ENTRY], "hasMore": False},
    "v1/users/retrieve": ADMIN,
    "v1/posts/change_status": {**POST, "status": "planned"},
    "v1/comments/create": {"id": "6a2889c586d7b8843bf4cf0d"},
    "v1/entries/create": {"id": "6a2889c586d7b8843bf4cf09"},
}
WRITES = {"v1/posts/change_status", "v1/comments/create", "v1/entries/create"}


class FakeCanny:
    def __init__(self, answers=ANSWERS):
        self.answers = dict(answers)
        self.requests = []           # (endpoint, body)
        self.queue = {}              # endpoint -> list of httpx.Response to return first

    def __call__(self, request: httpx.Request) -> httpx.Response:
        endpoint = request.url.path.removeprefix("/api/")
        body = json.loads(request.content)
        self.requests.append((endpoint, body))
        if self.queue.get(endpoint):
            return self.queue[endpoint].pop(0)
        return httpx.Response(200, json=self.answers[endpoint])

    def sent(self, endpoint):
        return [body for name, body in self.requests if name == endpoint]

    def wrote(self):
        return [name for name, _ in self.requests if name in WRITES]


@pytest.fixture
def canny(monkeypatch):
    fake = FakeCanny()
    monkeypatch.setenv("CANNY_API_KEY", "test-key")
    monkeypatch.setenv("CANNY_USER_ID", ADMIN["id"])
    monkeypatch.setattr(canny_commands, "_http", lambda: httpx.Client(transport=httpx.MockTransport(fake)))
    monkeypatch.setattr(canny_commands.time, "sleep", lambda seconds: fake.requests.append(("sleep", seconds)))
    return fake


def run(*args, input=None):
    return CliRunner().invoke(app, ["canny", *args], input=input)


# -- reads ---------------------------------------------------------------------

def test_boards_lists_id_name_and_count(canny):
    result = run("boards")
    assert result.exit_code == 0, result.output
    assert result.output.startswith("1 board\n")
    assert f"{BOARD['id']}    123 posts  public   Feature Requests  {BOARD['url']}" in result.output
    assert canny.sent("v1/boards/list") == [{"apiKey": "test-key"}]
    assert f"Next: co canny posts --board {BOARD['id']} --sort score" in result.output


def test_posts_sends_filters_and_prints_trimmed_rows(canny):
    result = run("posts", "--status", "open", "--sort", "score", "-n", "5")
    assert result.exit_code == 0, result.output
    assert canny.sent("v1/posts/list") == [{"apiKey": "test-key", "status": "open", "sort": "score", "limit": 5}]
    assert f"{POST['id']}    72 votes  open          Feature Requests  2026-09-30  Dark mode [beta]" in result.output
    assert "raise -n" in result.output
    assert f"Next: co canny post {POST['id']}" in result.output


def test_board_name_is_resolved_to_its_id(canny):
    result = run("posts", "--board", "feature requests")
    assert result.exit_code == 0, result.output
    assert canny.sent("v1/posts/list")[0]["boardID"] == BOARD["id"]


def test_unknown_board_name_names_the_boards_and_the_listing(canny):
    result = run("posts", "--board", "Nope")
    assert result.exit_code == 1
    assert 'No Canny board is named "Nope". Boards: Feature Requests' in result.output
    assert "Next: co canny boards" in result.output
    assert canny.sent("v1/posts/list") == []


def test_posts_json_has_the_same_fields_and_keeps_the_tip_off_stdout(canny):
    result = CliRunner().invoke(app, ["canny", "posts", "--json"])
    assert result.exit_code == 0, result.output
    data = json.loads(result.stdout)
    assert data == {"posts": [{"id": POST["id"], "title": POST["title"], "status": "open", "votes": 72,
                               "board": "Feature Requests", "created": POST["created"]}], "hasMore": True}
    assert "Next: co canny post" in result.stderr


def test_search_sorts_by_relevance(canny):
    result = run("search", "dark mode", "--json")
    assert result.exit_code == 0, result.output
    assert canny.sent("v1/posts/list") == [{"apiKey": "test-key", "sort": "relevance", "limit": 20, "search": "dark mode"}]


def test_post_shows_details_votes_and_comments(canny):
    result = run("post", POST["id"])
    assert result.exit_code == 0, result.output
    for text in ("Dark mode [beta]", "72 votes", "Please.", "Sam Admin (internal): Looking at it",
                 "1 comment, newest first, of 1"):
        assert text in result.output
    assert canny.sent("v2/comments/list")[0]["postID"] == POST["id"]
    assert f'Next: co canny comment {POST["id"]} "<your reply>"' in result.output


def test_post_json(canny):
    data = json.loads(CliRunner().invoke(app, ["canny", "post", POST["id"], "--json"]).stdout)
    assert data["votes"] == 72 and data["commentCount"] == 1
    assert data["comments"] == [{"id": COMMENT["id"], "author": "Sam Admin", "created": COMMENT["created"],
                                 "internal": True, "value": "Looking at it"}]


def test_changelog_lists_entries(canny):
    result = run("changelog", "-n", "3")
    assert result.exit_code == 0, result.output
    assert f"{ENTRY['id']}  published  2026-09-02  Faster search" in result.output
    assert canny.sent("v1/entries/list") == [{"apiKey": "test-key", "limit": 3}]
    assert 'Next: co canny changelog create "<title>" --details -' in result.output


def test_changelog_json(canny):
    data = json.loads(CliRunner().invoke(app, ["canny", "changelog", "--json"]).stdout)
    assert data["entries"][0]["title"] == "Faster search"


def test_check_reports_key_workspace_boards_and_acting_user(canny):
    result = run("check")
    assert result.exit_code == 0, result.output
    for text in ("accepted", "your shell", "acme.canny.io", "Feature Requests (123 posts)", "Sam Admin (admin)"):
        assert text in result.output
    assert "Next: co canny posts --status open --sort score" in result.output


def test_check_without_a_user_id_names_the_lookup(canny, monkeypatch):
    monkeypatch.delenv("CANNY_USER_ID")
    result = run("check")
    assert result.exit_code == 0, result.output
    assert "CANNY_USER_ID is not set" in result.output
    assert "Next: co canny check --email you@example.com" in result.output


def test_check_email_prints_the_env_set_line(canny):
    result = run("check", "--email", "sam@example.com")
    assert result.exit_code == 0, result.output
    assert canny.sent("v1/users/retrieve") == [{"apiKey": "test-key", "email": "sam@example.com"}]
    assert f"Next: co env set CANNY_USER_ID {ADMIN['id']}" in result.output


def test_check_email_of_a_non_admin_says_so(canny):
    canny.answers["v1/users/retrieve"] = {**ADMIN, "isAdmin": False}
    result = run("check", "--email", "voter@example.com")
    assert "NOT a Canny admin" in result.output
    assert "co env set CANNY_USER_ID" not in result.output


# -- writes: preview, then --yes ----------------------------------------------------

def test_status_previews_and_changes_nothing(canny):
    result = run("status", POST["id"], "in progress", "--comment", "Started", "--notify")
    assert result.exit_code == 0, result.output
    assert canny.wrote() == []
    assert "open -> in progress" in result.output and "72" in result.output
    assert "emails its non-admin voters" in result.output and "Nothing changed" in result.output
    assert f"Next: co canny status {POST['id']} 'in progress' --comment Started --notify --yes" in result.output


def test_status_preview_warns_when_the_status_is_unchanged(canny):
    result = run("status", POST["id"], "open")
    assert result.exit_code == 0, result.output
    assert "It already has this status: Canny will record nothing and email no one." in result.output


def test_status_yes_sends_changer_and_notify(canny):
    result = run("status", POST["id"], "planned", "--comment", "On the roadmap", "--notify", "--yes")
    assert result.exit_code == 0, result.output
    assert canny.sent("v1/posts/change_status") == [{
        "apiKey": "test-key", "postID": POST["id"], "changerID": ADMIN["id"], "status": "planned",
        "shouldNotifyVoters": True, "commentValue": "On the roadmap"}]
    assert "from open to planned; voters emailed" in result.output
    assert f"Next: co canny post {POST['id']}" in result.output


def test_status_without_user_id_fails_before_any_request(canny, monkeypatch):
    monkeypatch.delenv("CANNY_USER_ID")
    result = run("status", POST["id"], "planned", "--yes")
    assert result.exit_code == 1
    assert "CANNY_USER_ID" in result.output and "Next: co canny check --email you@example.com" in result.output
    assert canny.requests == []


def test_comment_previews_then_sends(canny):
    preview = run("comment", POST["id"], "Thanks!", "--internal")
    assert preview.exit_code == 0 and canny.wrote() == []
    assert "your team only" in preview.output
    assert f"Next: co canny comment {POST['id']} 'Thanks!' --internal --yes" in preview.output
    sent = run("comment", POST["id"], "Thanks!", "--internal", "--yes")
    assert sent.exit_code == 0, sent.output
    assert canny.sent("v1/comments/create") == [{"apiKey": "test-key", "postID": POST["id"],
                                                 "authorID": ADMIN["id"], "value": "Thanks!", "internal": True}]


def test_public_comment_leaves_internal_out(canny):
    run("comment", POST["id"], "Thanks!", "--yes")
    assert "internal" not in canny.sent("v1/comments/create")[0]


def test_changelog_create_previews_without_any_request(canny):
    result = run("changelog", "create", "Dark mode", "--details", "-", "--publish", input="It is here.\n")
    assert result.exit_code == 0, result.output
    assert canny.requests == []
    assert "published now" in result.output and "It is here." in result.output
    assert "Next: co canny changelog create 'Dark mode' --details - --publish --yes" in result.output


def test_changelog_create_yes_reads_stdin(canny):
    result = run("changelog", "create", "Dark mode", "--details", "-", "--yes", input="It is here.\n")
    assert result.exit_code == 0, result.output
    assert canny.sent("v1/entries/create") == [{"apiKey": "test-key", "title": "Dark mode",
                                                "details": "It is here.\n", "published": False}]
    assert "(draft)" in result.output and "Next: co canny changelog" in result.output


# -- failures --------------------------------------------------------------------------

def test_missing_key_names_the_env_set_command(canny, monkeypatch):
    monkeypatch.delenv("CANNY_API_KEY")
    result = run("boards")
    assert result.exit_code == 1
    assert "CANNY_API_KEY is not set" in result.output and "Settings → API" in result.output
    assert "Next: co env set CANNY_API_KEY <key> --secret" in result.output
    assert canny.requests == []


def test_key_in_the_selected_env_file_is_used(canny, monkeypatch):
    monkeypatch.delenv("CANNY_API_KEY")
    (Path.home() / ".co").mkdir(exist_ok=True)
    (Path.home() / ".co" / "keys.env").write_text("CANNY_API_KEY=from-file\n")
    result = run("check")
    assert result.exit_code == 0, result.output
    assert canny.sent("v1/boards/list")[0]["apiKey"] == "from-file"
    assert "~/.co/keys.env" in result.output


def test_key_saved_with_secret_is_decrypted(canny, monkeypatch):
    from connectonion.secret_store import put
    monkeypatch.delenv("CANNY_API_KEY")
    co = Path.home() / ".co"
    (co / "keys").mkdir(parents=True, exist_ok=True)
    (co / "keys" / "agent.key").write_bytes(bytes(range(32)))
    put(co, "CANNY_API_KEY", "from-store")
    result = run("check")
    assert result.exit_code == 0, result.output
    assert canny.sent("v1/boards/list")[0]["apiKey"] == "from-store"
    assert "the encrypted store" in result.output


def test_api_error_is_reported_with_a_next_command(canny):
    canny.queue["v1/posts/retrieve"] = [httpx.Response(400, json={"error": "invalid post id"})]
    result = run("post", "nope")
    assert result.exit_code == 1
    assert "Canny refused v1/posts/retrieve (HTTP 400): invalid post id" in result.output
    assert "Next: co canny posts" in result.output


def test_rejected_key_names_the_env_set_command(canny):
    canny.queue["v1/boards/list"] = [httpx.Response(401, json={"error": "invalid api key"})]
    result = run("boards")
    assert result.exit_code == 1
    assert "Canny rejected the API key" in result.output
    assert "Next: co env set CANNY_API_KEY <key> --secret" in result.output


def test_429_is_waited_out_once(canny):
    canny.queue["v1/boards/list"] = [httpx.Response(429, headers={"Retry-After": "3"}, json={"error": "slow down"})]
    result = run("boards")
    assert result.exit_code == 0, result.output
    assert ("sleep", 3) in canny.requests
    assert len(canny.sent("v1/boards/list")) == 2


def test_second_429_is_reported_with_the_same_command(canny, monkeypatch):
    monkeypatch.setattr("sys.argv", ["co", "canny", "boards"])
    limited = httpx.Response(429, headers={"Retry-After": "3"}, json={"error": "slow down"})
    canny.queue["v1/boards/list"] = [limited, limited]
    result = run("boards")
    assert result.exit_code == 1
    assert "HTTP 429" in result.output and "Next: co canny boards" in result.output
    assert len(canny.sent("v1/boards/list")) == 2


def test_long_retry_after_is_reported_not_waited(canny, monkeypatch):
    monkeypatch.setattr("sys.argv", ["co", "canny", "boards"])
    canny.queue["v1/boards/list"] = [httpx.Response(429, headers={"Retry-After": "1800"}, json={"error": "slow down"})]
    result = run("boards")
    assert result.exit_code == 1
    assert "1800s" in result.output
    assert not [r for r in canny.requests if r[0] == "sleep"]


def test_bare_group_prints_help_and_the_first_step():
    result = run()
    assert result.exit_code == 0
    assert "co canny check" in result.output.splitlines()[-1]


def test_counts_are_singular_for_one(canny):
    canny.answers["v1/posts/list"] = {"posts": [{**POST, "score": 1}], "hasMore": False}
    result = run("posts")
    assert result.output.startswith("1 post\n")
    assert f"{POST['id']}     1 vote   open" in result.output
    assert "1 changelog entry," in run("changelog").output
    canny.answers["v1/boards/list"] = {"boards": [{**BOARD, "postCount": 1}]}
    assert "Feature Requests (1 post)" in run("check").output


def test_empty_posts_point_at_the_boards_not_the_same_list(canny):
    canny.answers["v1/posts/list"] = {"posts": [], "hasMore": False}
    result = run("posts", "--sort", "score")
    assert result.exit_code == 0
    assert "0 posts" in result.output and "Next: co canny boards" in result.output


def test_empty_search_points_at_browsing(canny):
    canny.answers["v1/posts/list"] = {"posts": [], "hasMore": False}
    assert "Next: co canny posts --sort score" in run("search", "nothing like this").output


def test_boards_with_no_posts_say_where_to_add_one(canny):
    canny.answers["v1/boards/list"] = {"boards": [{**BOARD, "postCount": 0}]}
    result = run("boards")
    assert f"Add one on the board's page, {BOARD['url']}" in result.output
    assert "Next: co canny boards" in result.output and "co canny posts --board" not in result.output


def test_internal_comment_on_a_plan_without_them_offers_the_public_one(canny):
    canny.queue["v1/comments/create"] = [httpx.Response(400, json={"error": "plan does not support internal comments"})]
    result = run("comment", POST["id"], "Thanks!", "--internal", "--yes")
    assert result.exit_code == 1
    assert "plan does not support internal comments" in result.output
    assert "the comment is public" in result.output
    assert f"Next: co canny comment {POST['id']} 'Thanks!'\n" in result.output


def test_other_comment_refusals_point_at_the_post(canny):
    canny.queue["v1/comments/create"] = [httpx.Response(400, json={"error": "invalid value"})]
    result = run("comment", POST["id"], "Thanks!", "--yes")
    assert f"Next: co canny post {POST['id']}" in result.output


def test_the_skill_names_every_command_and_only_those():
    import re
    from typer.main import get_command
    visible = set(get_command(app).commands["canny"].commands)
    skill = (Path(__file__).resolve().parents[2] / "connectonion/useful_skills/co-canny/SKILL.md").read_text()
    assert visible == set(re.findall(r"co canny ([a-z]+)", skill))
