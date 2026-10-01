"""co linear against a fake Linear: every command, name resolution, preview vs --yes, errors, --json.

LLM-Note: Tests for connectonion/cli/commands/linear_commands.py and linear_api.py with Linear's
GraphQL endpoint behind httpx.MockTransport. The fake answers by the root field each query asks
for, from one small workspace (two teams, their states, labels, two members, two issues), and
records every request so a test can assert what was sent — and that a preview sent no mutation.
"""

import json
import re
from pathlib import Path

import click
import httpx
import pytest
from typer.main import get_command
from typer.testing import CliRunner

from connectonion.cli.commands import linear_api as api
from connectonion.cli.main import app

TEAMS = [{"id": "t-eng", "key": "ENG", "name": "Engineering"}, {"id": "t-ops", "key": "OPS", "name": "Operations"}]
STATES = {
    "t-eng": [{"id": "s-todo", "name": "Todo", "type": "unstarted", "position": 1, "team": {"key": "ENG"}},
              {"id": "s-prog", "name": "In Progress", "type": "started", "position": 2, "team": {"key": "ENG"}},
              {"id": "s-done", "name": "Done", "type": "completed", "position": 3, "team": {"key": "ENG"}}],
    "t-ops": [{"id": "s-ops-done", "name": "Done", "type": "completed", "position": 1, "team": {"key": "OPS"}}],
}
LABELS = [{"id": "l-bug", "name": "Bug", "isGroup": False, "team": None},
          {"id": "l-auth", "name": "auth", "isGroup": False, "team": {"id": "t-eng", "key": "ENG"}},
          {"id": "l-ops", "name": "pager", "isGroup": False, "team": {"id": "t-ops", "key": "OPS"}},
          {"id": "l-group", "name": "Area", "isGroup": True, "team": None}]
USERS = [{"id": "u-me", "name": "Aaron", "email": "aaron@example.com", "active": True},
         {"id": "u-bo", "name": "Bo", "email": "bo@example.com", "active": True},
         {"id": "u-gone", "name": "Gone", "email": "gone@example.com", "active": False}]
PROJECTS = [{"name": "Q4 Launch", "url": "https://linear.app/x/project/q4", "updatedAt": "2026-09-30T00:00:00Z",
             "status": {"name": "In Progress"}, "teams": {"nodes": [{"key": "ENG"}]}}]


def node(identifier, title, state="Todo", assignee=USERS[0], priority=(2, "High"), updated="2026-09-30T08:00:00.000Z"):
    return {"identifier": identifier, "title": title, "priority": priority[0], "priorityLabel": priority[1],
            "updatedAt": updated, "state": {"name": state},
            "assignee": assignee and {"name": assignee["name"], "email": assignee["email"]}}


ISSUES = [node("ENG-2", "Login redirect loops", "In Progress"),
          node("ENG-1", "Old crash", assignee=None, priority=(0, "No priority"), updated="2026-09-01T08:00:00.000Z")]
DETAIL = {**ISSUES[0], "id": "uuid-eng-2", "description": "Steps:\n1. log in", "url": "https://linear.app/x/issue/ENG-2",
          "createdAt": "2026-09-20T00:00:00.000Z", "team": TEAMS[0], "project": {"name": "Q4 Launch"},
          "labels": {"nodes": [{"name": "Bug"}]},
          "comments": {"nodes": [{"body": "second", "createdAt": "2026-09-29T10:00:00.000Z", "user": {"name": "Bo"}},
                                 {"body": "first", "createdAt": "2026-09-28T10:00:00.000Z", "user": None}]}}


def answer(query: str, variables: dict) -> dict:
    """The fake workspace's reply, chosen by the root field the query selects."""
    if "issueCreate" in query:
        return {"issueCreate": {"success": True, "issue": {"identifier": "ENG-3", "title": variables["input"]["title"],
                                                           "url": "https://linear.app/x/issue/ENG-3"}}}
    if "issueUpdate" in query:
        return {"issueUpdate": {"success": True, "issue": {**ISSUES[0], "url": DETAIL["url"], "state": {"name": "Done"}}}}
    if "commentCreate" in query:
        return {"commentCreate": {"success": True, "comment": {"id": "c-1", "url": DETAIL["url"] + "#comment-c-1"}}}
    if "searchIssues" in query:
        return {"searchIssues": {"nodes": ISSUES[:1]}}
    if "issue(id" in query:
        if variables["id"] != "ENG-2":
            raise LookupError
        return {"issue": DETAIL}
    if "issues(" in query:
        return {"issues": {"nodes": ISSUES}}
    if "team(id" in query and "states(" in query:
        return {"team": {"states": {"nodes": STATES[variables["id"]]}}}
    if "team(id" in query and "projects(" in query:
        return {"team": {"projects": {"nodes": PROJECTS}}}
    if "workflowStates" in query:
        return {"workflowStates": {"nodes": STATES["t-eng"] + STATES["t-ops"]}}
    if "projects(" in query:
        return {"projects": {"nodes": PROJECTS}}
    if "teams(" in query:
        return {"teams": {"nodes": TEAMS}}
    if "issueLabels" in query:
        return {"issueLabels": {"nodes": LABELS}}
    if "users(" in query:
        return {"users": {"nodes": USERS}}
    if "viewer" in query:
        return {"viewer": {"id": "u-me", "name": "Aaron", "email": "aaron@example.com"},
                "organization": {"name": "Acme", "urlKey": "acme"}}
    raise AssertionError(f"unexpected query: {query}")


@pytest.fixture
def linear(monkeypatch):
    """Linear behind MockTransport. `linear.sent` holds every (query, variables); `linear.reply` can override."""
    state = type("Linear", (), {"sent": [], "requests": [], "reply": None})()

    def handler(request):
        body = json.loads(request.content)
        state.requests.append(request)
        state.sent.append((body["query"], body["variables"]))
        if state.reply:
            return state.reply(body)
        try:
            return httpx.Response(200, json={"data": answer(body["query"], body["variables"])})
        except LookupError:
            return httpx.Response(200, json={"data": None, "errors": [{"message": "Entity not found: Issue",
                                                                       "extensions": {"type": "invalid input"}}]})

    monkeypatch.setattr(api, "_http", lambda: httpx.Client(transport=httpx.MockTransport(handler)))
    monkeypatch.setenv("LINEAR_API_KEY", "lin_api_test")
    return state


def run(*args, input=None):
    return CliRunner().invoke(app, ["linear", *args], input=input)


def mutations(linear):
    return [(q, v) for q, v in linear.sent if q.lstrip().startswith("mutation")]


def last_line(text):
    return text.strip().splitlines()[-1]


# -- reads -----------------------------------------------------------------

def test_issues_mine_sends_the_key_and_lists_open_issues_with_a_next_step(linear):
    result = run("issues", "--mine")
    assert result.exit_code == 0, result.output
    request = linear.requests[0]
    assert request.url == "https://api.linear.app/graphql"
    assert request.headers["authorization"] == "lin_api_test"            # a personal key is sent bare, not as Bearer
    query, variables = linear.sent[-1]
    assert variables["filter"] == {"assignee": {"isMe": {"eq": True}}, "state": {"type": {"nin": ["completed", "canceled"]}}}
    assert variables["first"] == 20 and "orderBy: updatedAt" in query
    assert "2 open issues assigned to you" in result.stdout
    assert "ENG-2" in result.stdout and "In Progress" in result.stdout and "Login redirect loops" in result.stdout
    assert "2026-09-30" in result.stdout and "Aaron" in result.stdout and "High" in result.stdout
    assert last_line(result.stdout) == "Next: co linear issue ENG-2"


def test_issues_resolves_team_state_and_project_names_case_insensitively(linear):
    result = run("issues", "--team", "eng", "--state", "in progress", "--project", "q4 launch", "-n", "5")
    assert result.exit_code == 0, result.output
    _, variables = linear.sent[-1]
    assert variables["filter"] == {"team": {"key": {"eq": "ENG"}}, "state": {"name": {"eq": "In Progress"}},
                                   "project": {"name": {"eq": "Q4 Launch"}}}
    assert variables["first"] == 5


def test_issues_state_without_team_is_checked_against_every_team(linear):
    assert run("issues", "--state", "done").exit_code == 0
    assert linear.sent[-1][1]["filter"] == {"state": {"name": {"eq": "Done"}}}


@pytest.mark.parametrize("args, valid, command", [
    (["issues", "--team", "NOPE"], "ENG, OPS", "co linear teams"),
    (["issues", "--team", "ENG", "--state", "Shipped"], "Done, In Progress, Todo", "co linear states --team ENG"),
    (["issues", "--state", "Shipped"], "Done, In Progress, Todo", "co linear states"),
    (["issues", "--project", "Nope"], "Q4 Launch", "co linear projects"),
])
def test_an_unknown_name_exits_1_listing_the_valid_ones_and_the_command_to_list_them(linear, args, valid, command):
    result = run(*args)
    assert result.exit_code == 1
    assert f"Valid: {valid}" in result.stderr
    assert last_line(result.stderr) == f"Next: {command}"
    assert not any("issues(" in q for q, _ in linear.sent)              # nothing listed on a wrong name


def test_issues_json_is_the_same_fields_and_stdout_stays_parseable(linear):
    result = run("issues", "--json")
    assert result.exit_code == 0, result.output
    rows = json.loads(result.stdout)
    assert rows[0] == {"id": "ENG-2", "title": "Login redirect loops", "state": "In Progress", "assignee": "Aaron",
                       "priority": "High", "updated": "2026-09-30T08:00:00.000Z"}
    assert rows[1]["assignee"] is None
    assert "Next: co linear issue ENG-2" in result.stderr


def test_an_empty_list_names_a_command_too(linear, monkeypatch):
    monkeypatch.setattr(api, "issues", lambda where, first: [])
    result = run("issues", "--mine")
    assert result.exit_code == 0 and "0 open issues" in result.stdout
    assert last_line(result.stdout) == 'Next: co linear search "<words>"'


def test_issue_shows_details_and_comments_oldest_first(linear):
    result = run("issue", "ENG-2")
    assert result.exit_code == 0, result.output
    out = result.stdout
    for text in ("Login redirect loops", "In Progress", "Q4 Launch", "Bug", DETAIL["url"], "1. log in"):
        assert text in out
    assert out.index("first") < out.index("second") and "(integration)" in out
    assert last_line(out) == 'Next: co linear comment ENG-2 "<your reply>"'


def test_issue_json(linear):
    detail = json.loads(run("issue", "ENG-2", "--json").stdout)
    assert detail["id"] == "ENG-2" and detail["team"] == "ENG" and detail["labels"] == ["Bug"]
    assert [c["body"] for c in detail["comments"]] == ["first", "second"]
    assert set(api.row(DETAIL)) <= set(detail)


def test_an_unknown_issue_says_so_and_names_search(linear):
    result = run("issue", "ENG-999")
    assert result.exit_code == 1
    assert "No issue ENG-999 in this workspace" in result.stderr
    assert last_line(result.stderr) == 'Next: co linear search "<words from its title>"'


def test_search_uses_linear_full_text_search(linear):
    result = run("search", "login", "-n", "3")
    assert result.exit_code == 0, result.output
    query, variables = linear.sent[-1]
    assert "searchIssues(term: $term" in query and variables == {"term": "login", "first": 3}
    assert "ENG-2" in result.stdout and last_line(result.stdout) == "Next: co linear issue ENG-2"
    assert json.loads(run("search", "login", "--json").stdout)[0]["id"] == "ENG-2"


@pytest.mark.parametrize("args, shows, tip", [
    (["teams"], ["ENG", "Engineering", "OPS"], "co linear issues --team ENG"),
    (["projects"], ["Q4 Launch", "In Progress"], 'co linear issues --project "Q4 Launch"'),
    (["projects", "--team", "ENG"], ["Q4 Launch"], 'co linear issues --project "Q4 Launch"'),
    (["states", "--team", "ENG"], ["Todo", "In Progress", "Done", "started"], 'co linear issues --team ENG --state "Todo"'),
    (["labels", "--team", "ENG"], ["Bug", "auth", "workspace"], 'co linear create "<title>" --team ENG --label "Bug"'),
    (["users"], ["Bo", "bo@example.com"], "co linear update <ENG-123> --assignee aaron@example.com"),
    (["check"], ["Acme", "linear.app/acme", "Aaron <aaron@example.com>"], "co linear issues --mine"),
])
def test_listings_show_the_names_other_commands_take(linear, args, shows, tip):
    result = run(*args)
    assert result.exit_code == 0, result.output
    for text in shows:
        assert text in result.stdout
    assert last_line(result.stdout) == f"Next: {tip}"


def test_listings_leave_out_what_cannot_be_used(linear):
    assert "pager" not in run("labels", "--team", "ENG").stdout       # another team's label
    assert "Area" not in run("labels").stdout                          # a label group is not assignable
    assert "gone@example.com" not in run("users").stdout               # a deactivated member


def test_states_lists_every_team_in_board_order(linear):
    rows = json.loads(run("states", "--json").stdout)
    assert [(r["team"], r["name"]) for r in rows] == [("ENG", "Todo"), ("ENG", "In Progress"), ("ENG", "Done"), ("OPS", "Done")]


@pytest.mark.parametrize("args", [["teams"], ["projects"], ["states"], ["labels"], ["users"]])
def test_every_listing_has_json(linear, args):
    result = run(*args, "--json")
    assert result.exit_code == 0 and isinstance(json.loads(result.stdout), list)


# -- writes: preview unless --yes ------------------------------------------

def test_create_previews_with_names_resolved_and_sends_nothing(linear):
    result = run("create", "Login loops", "--team", "eng", "--label", "bug", "--label", "AUTH",
                 "--assignee", "me", "--priority", "high")
    assert result.exit_code == 0, result.output
    assert mutations(linear) == []
    out = result.stdout
    assert "Preview" in out and "Nothing changed in Linear" in out
    assert "ENG (Engineering)" in out and "Aaron <aaron@example.com>" in out and "Bug, auth" in out and "High" in out
    assert last_line(out) == ("Next: co linear create 'Login loops' --team ENG --assignee me --priority high "
                              "--label bug --label AUTH --yes")


def test_create_with_yes_sends_ids_and_prints_the_new_id(linear):
    result = run("create", "Login loops", "--team", "ENG", "--label", "Bug", "--assignee", "bo@example.com",
                 "--priority", "1", "--description", "-", "--yes", input="Steps to reproduce\n")
    assert result.exit_code == 0, result.output
    [(_, variables)] = mutations(linear)
    assert variables["input"] == {"teamId": "t-eng", "title": "Login loops", "description": "Steps to reproduce\n",
                                  "assigneeId": "u-bo", "priority": 1, "labelIds": ["l-bug"]}
    assert "Created ENG-3" in result.stdout and last_line(result.stdout) == "Next: co linear issue ENG-3"


@pytest.mark.parametrize("args, said, command", [
    (["--label", "nope"], "Valid: Bug, auth", "co linear labels --team ENG"),
    (["--label", "pager"], "Valid: Bug, auth", "co linear labels --team ENG"),
    (["--assignee", "who@example.com"], "Valid: aaron@example.com, bo@example.com", "co linear users"),
    (["--priority", "9"], "Valid: 0 none, 1 urgent, 2 high, 3 medium, 4 low", "co linear create --help"),
])
def test_create_refuses_an_unknown_name_before_creating_anything(linear, args, said, command):
    result = run("create", "T", "--team", "ENG", *args, "--yes")
    assert result.exit_code == 1
    assert said in result.stderr and last_line(result.stderr) == f"Next: {command}"
    assert mutations(linear) == []


def test_update_previews_each_change_from_and_to(linear):
    result = run("update", "ENG-2", "--state", "done", "--assignee", "bo@example.com", "--priority", "urgent")
    assert result.exit_code == 0, result.output
    assert mutations(linear) == []
    out = result.stdout
    assert "In Progress → Done" in out and "Aaron → Bo" in out and "High → Urgent" in out
    assert last_line(out) == "Next: co linear update ENG-2 --state done --assignee bo@example.com --priority urgent --yes"


def test_update_with_yes_resolves_the_state_in_the_issues_own_team(linear):
    result = run("update", "ENG-2", "--state", "Done", "--yes")
    assert result.exit_code == 0, result.output
    [(_, variables)] = mutations(linear)
    assert variables == {"id": "uuid-eng-2", "input": {"stateId": "s-done"}}       # ENG's Done, not OPS's
    assert "Updated ENG-2" in result.stdout and last_line(result.stdout) == "Next: co linear issue ENG-2"


def test_update_names_the_teams_states_when_the_state_is_unknown(linear):
    result = run("update", "ENG-2", "--state", "Shipped", "--yes")
    assert result.exit_code == 1 and "Valid: Done, In Progress, Todo" in result.stderr
    assert last_line(result.stderr) == "Next: co linear states --team ENG"
    assert mutations(linear) == []


def test_update_with_nothing_to_change_exits_2_naming_its_help(linear):
    result = run("update", "ENG-2")
    assert result.exit_code == 2 and "Next: co linear update --help" in result.output
    assert linear.sent == []


def test_comment_previews_then_sends_with_yes(linear):
    preview = run("comment", "ENG-2", "Fixed in #42")
    assert preview.exit_code == 0 and mutations(linear) == []
    assert "Fixed in #42" in preview.stdout
    assert last_line(preview.stdout) == "Next: co linear comment ENG-2 'Fixed in #42' --yes"
    sent = run("comment", "ENG-2", "-", "--yes", input="Long\nreply")
    assert sent.exit_code == 0, sent.output
    [(_, variables)] = mutations(linear)
    assert variables["input"] == {"issueId": "uuid-eng-2", "body": "Long\nreply"}
    assert "Commented on ENG-2" in sent.stdout and last_line(sent.stdout) == "Next: co linear issue ENG-2"


# -- the key and Linear's errors -------------------------------------------

def test_a_missing_key_names_the_command_and_where_to_create_one(linear, monkeypatch):
    monkeypatch.delenv("LINEAR_API_KEY")
    result = run("issues", "--mine")
    assert result.exit_code == 1
    assert "LINEAR_API_KEY is not set" in result.stderr
    assert "Linear Settings → Security & access → Personal API keys" in result.stderr
    assert last_line(result.stderr) == "Next: co env set LINEAR_API_KEY lin_api_... --secret"
    assert linear.sent == []


def test_a_key_saved_with_secret_is_read_from_the_encrypted_store(linear, monkeypatch):
    monkeypatch.delenv("LINEAR_API_KEY")
    from connectonion import secret_store
    monkeypatch.setattr(secret_store, "stored_names", lambda co_dir: ["linear_api_key"])
    monkeypatch.setattr(secret_store, "get", lambda co_dir, name: "lin_api_from_store")
    assert run("check").exit_code == 0
    assert linear.requests[0].headers["authorization"] == "lin_api_from_store"


def test_a_rejected_key_names_the_command_to_replace_it(linear):
    # Linear's reply to a bad key, as curl got it on 2026-10-01 (HTTP 401).
    linear.reply = lambda body: httpx.Response(401, json={"errors": [{
        "message": "Authentication required, not authenticated",
        "extensions": {"type": "authentication error", "code": "AUTHENTICATION_ERROR", "statusCode": 401,
                       "userPresentableMessage": "You need to authenticate to access this operation."}}]})
    result = run("check")
    assert result.exit_code == 1
    assert "Linear rejected LINEAR_API_KEY: You need to authenticate to access this operation. Make" in result.stderr
    assert last_line(result.stderr) == "Next: co env set LINEAR_API_KEY lin_api_... --secret"


def test_a_graphql_error_prints_linears_message_and_a_next_step(linear):
    linear.reply = lambda body: httpx.Response(400, json={"errors": [{
        "message": "Rate limit exceeded", "extensions": {"code": "RATELIMITED",
                                                         "userPresentableMessage": "Too many requests, try later"}}]})
    result = run("issues")
    assert result.exit_code == 1
    assert "Linear: Too many requests, try later" in result.stderr
    assert last_line(result.stderr) == "Next: co linear check"


def test_bare_co_linear_prints_its_help_without_calling_linear(linear):
    result = run()
    page = click.unstyle(result.stdout)          # CI's GITHUB_ACTIONS turns Rich's colour on
    assert result.exit_code == 0 and "Usage:" in page and "comment" in page
    assert linear.sent == []


def test_every_command_the_skill_names_exists():
    leaves = set(get_command(app).commands["linear"].commands)
    skill = (Path(__file__).resolve().parents[2] / "connectonion/useful_skills/co-linear/SKILL.md").read_text()
    named = set(re.findall(r"co linear ([a-z]+)", skill))
    assert named and named <= leaves
