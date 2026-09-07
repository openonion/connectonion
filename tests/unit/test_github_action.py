import io
import json

import pytest

import connectonion.cli.github_action as action_module
from connectonion.cli.github_action import (
    COMMENT_MARKER,
    ActionError,
    GitHubClient,
    _invoke_json_review,
    render_comment,
    resolve_pr_number,
    run_review,
)


class Response(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


class ReviewClient:
    def __init__(self):
        self.calls = []

    def read_pull_request(self, pr_number):
        self.calls.append(pr_number)
        return f"evidence for {pr_number}"


def test_json_review_uses_the_333_agent_factory_seam(tmp_path, monkeypatch):
    class Tools:
        def get_instance(self, name, default=None):
            return default

    class Agent:
        system_prompt = "review system"
        tools = Tools()

        def input(self, prompt, session=None):
            self.current_session = {
                **session,
                "messages": session["messages"]
                + [{"role": "user", "content": prompt}],
                "trace": [{"type": "turn_result", "reason": "natural"}],
                "turn": 1,
            }
            return "review result"

    calls = []

    def factory(*args, **kwargs):
        calls.append((args, kwargs))
        return Agent()

    monkeypatch.setattr("connectonion.cli.co_ai.agent.GLOBAL_CO_DIR", tmp_path)

    stdout, exit_code = _invoke_json_review("/review-pr 5", "co/test", factory)

    assert exit_code == 0
    assert json.loads(stdout) == {
        "session_id": None,
        "result": "review result",
        "outcome": "natural",
        "error": None,
    }
    assert calls == [(("co/test", 4, True, 1), {"resumable": True})]
    assert not (tmp_path / "ai" / "sessions").exists()


def test_pr_number_prefers_input_and_falls_back_to_event(tmp_path):
    event = tmp_path / "event.json"
    event.write_text(json.dumps({"pull_request": {"number": 42}}), encoding="utf-8")

    assert resolve_pr_number("7", str(event)) == 7
    assert resolve_pr_number(None, str(event)) == 42


def test_pr_number_rejects_an_unrelated_event(tmp_path):
    event = tmp_path / "event.json"
    event.write_text("[]", encoding="utf-8")

    with pytest.raises(ActionError, match="positive pull request"):
        resolve_pr_number(None, str(event))


@pytest.mark.parametrize("value", ["", "0", "-1", "1.5"])
def test_pr_number_rejects_noncanonical_values(value):
    with pytest.raises(ActionError, match="positive pull request"):
        resolve_pr_number(value, None)


def test_review_resolves_the_canonical_skill_with_one_read_only_tool():
    client = ReviewClient()

    def invoke(prompt, model, factory):
        from connectonion.useful_plugins.skills import handle_skill_invocation

        assert prompt == "/review-pr 12"
        agent = factory(model, 20, True, 1, resumable=True)
        assert agent.tools.names() == ["read_pull_request"]
        reader = agent.tools.get("read_pull_request")
        assert reader() == "evidence for 12"
        assert reader() == (
            "Pull request evidence was already provided; use the prior tool result."
        )
        agent.current_session = {
            "messages": [{"role": "user", "content": prompt}],
            "trace": [],
            "turn": 1,
        }

        handle_skill_invocation(agent)

        loaded = agent.current_session["messages"][-1]["content"]
        assert "# PR Review Skill" in loaded
        assert "## Arguments\n12" in loaded
        return '{"session_id":"session-1","result":"Looks good","error":null}', 0

    assert run_review(12, "co/test-model", client, invoke) == (
        "Looks good",
        "session-1",
    )
    assert client.calls == [12]


@pytest.mark.parametrize(
    ("stdout", "returncode", "message"),
    [
        ("progress, not json", 0, "JSON result envelope"),
        ('{"session_id":null,"result":null,"error":"provider down"}', 1, "provider down"),
        ('{"session_id":null,"result":null,"error":null}', 0, "no review result"),
        ('{"session_id":null,"result":"   ","error":null}', 0, "no review result"),
    ],
)
def test_review_fails_closed(stdout, returncode, message):
    with pytest.raises(ActionError, match=message):
        run_review(
            12,
            "co/test",
            ReviewClient(),
            lambda *args: (stdout, returncode),
        )


@pytest.mark.parametrize(
    "envelope",
    [
        {"result": "missing fields"},
        {"session_id": "s", "result": "extra field", "error": None, "trace": []},
    ],
)
def test_review_requires_the_exact_json_envelope(envelope):
    with pytest.raises(ActionError, match="invalid JSON result envelope"):
        run_review(
            12,
            "co/test",
            ReviewClient(),
            lambda *args: (json.dumps(envelope), 0),
        )


def test_review_error_is_bounded_before_it_reaches_logs():
    envelope = json.dumps({"session_id": None, "result": None, "error": "x" * 2_000})

    with pytest.raises(ActionError) as caught:
        run_review(
            12,
            "co/test",
            ReviewClient(),
            lambda *args: (envelope, 1),
        )

    assert len(str(caught.value)) < 550


def test_comment_is_bounded_without_splitting_utf8():
    body = render_comment("🧅" * 40_000, "session")

    assert body.startswith(COMMENT_MARKER)
    assert len(body.encode("utf-8")) <= 60_000
    assert "Review truncated" in body


def test_transient_review_comment_does_not_advertise_a_session():
    body = render_comment("Looks good", None)

    assert "Looks good" in body
    assert "ConnectOnion session" not in body


def test_model_reader_uses_only_fixed_get_requests_for_one_pr():
    requests = []

    def open_url(request, timeout):
        requests.append(request)
        if request.get_header("Accept") == "application/vnd.github.v3.diff":
            return Response(b"diff --git a/a.py b/a.py\n")
        if request.full_url.endswith("/pulls/8"):
            payload = {
                "number": 8,
                "title": "Change",
                "head": {"sha": "abc", "ref": "feature", "repo": {"full_name": "owner/repo"}},
                "base": {"sha": "def", "ref": "main", "repo": {"full_name": "owner/repo"}},
            }
        elif "/check-runs" in request.full_url:
            checks = [{"name": f"test-{number}", "conclusion": "success"} for number in range(100)]
            if "page=2" in request.full_url:
                checks = [{"name": "final-test", "conclusion": "success"}]
            payload = {"check_runs": checks}
        else:
            payload = []
        return Response(json.dumps(payload).encode())

    client = GitHubClient("write-token-not-exposed-to-model", "owner/repo", open_url=open_url)

    evidence = client.read_pull_request(8)

    assert "COMPLETE DIFF" in evidence
    assert '"title": "Change"' in evidence
    assert '"review_comments": []' in evidence
    assert '"statuses": []' in evidence
    assert '"final-test"' in evidence
    assert all(request.method == "GET" for request in requests)
    assert all(request.data is None for request in requests)
    assert all("/repos/owner/repo/" in request.full_url for request in requests)
    assert all(b"write-token-not-exposed-to-model" not in (request.data or b"") for request in requests)
    urls = [request.full_url for request in requests]
    assert any("/pulls/8/comments" in url for url in urls)
    assert any("/commits/abc/statuses" in url for url in urls)
    assert any("/check-runs" in url and "page=2" in url for url in urls)


def test_first_run_creates_comment_and_sends_token_only_as_header():
    requests = []

    def open_url(request, timeout):
        requests.append(request)
        if request.method == "GET":
            return Response(b"[]")
        return Response(b'{"html_url":"https://github.test/comment/1"}')

    client = GitHubClient("top-secret", "owner/repo", open_url=open_url)

    assert client.upsert_review_comment(8, "review") == "https://github.test/comment/1"
    assert [request.method for request in requests] == ["GET", "POST"]
    assert requests[1].full_url.endswith("/repos/owner/repo/issues/8/comments")
    assert requests[1].get_header("Authorization") == "Bearer top-secret"
    assert b"top-secret" not in requests[1].data


def test_rerun_updates_only_the_github_actions_marker():
    comments = [
        {"id": 1, "body": COMMENT_MARKER + " copied", "user": {"type": "User", "login": "person"}},
        {"id": 3, "body": COMMENT_MARKER + " other bot", "user": {"type": "Bot", "login": "other[bot]"}},
        {"id": 2, "body": COMMENT_MARKER + " old", "user": {"type": "Bot", "login": "github-actions[bot]"}},
    ]
    requests = []

    def open_url(request, timeout):
        requests.append(request)
        if request.method == "GET":
            return Response(json.dumps(comments).encode())
        return Response(b'{"html_url":"https://github.test/comment/2"}')

    client = GitHubClient("token", "owner/repo", open_url=open_url)

    client.upsert_review_comment(8, "new review")
    assert [request.method for request in requests] == ["GET", "PATCH"]
    assert requests[1].full_url.endswith("/repos/owner/repo/issues/comments/2")
    assert json.loads(requests[1].data) == {"body": "new review"}


def test_marked_comment_requires_a_numeric_github_id():
    comments = [
        {"body": COMMENT_MARKER, "user": {"type": "Bot", "login": "github-actions[bot]"}}
    ]

    def open_url(request, timeout):
        return Response(json.dumps(comments).encode())

    client = GitHubClient("token", "owner/repo", open_url=open_url)

    with pytest.raises(ActionError, match="invalid marked comment"):
        client.upsert_review_comment(8, "new review")


def test_comment_search_paginates_before_creating():
    pages = []

    def open_url(request, timeout):
        if request.method == "GET":
            pages.append(request.full_url)
            payload = [{"id": i, "body": "human", "user": {"type": "User"}} for i in range(100)]
            if "page=2" in request.full_url:
                payload = []
            return Response(json.dumps(payload).encode())
        return Response(b'{"html_url":"https://github.test/comment/new"}')

    client = GitHubClient("token", "owner/repo", open_url=open_url)
    client.upsert_review_comment(8, "new review")

    assert len(pages) == 2
    assert "page=2" in pages[1]


def test_evidence_response_fails_closed_above_the_byte_limit(monkeypatch):
    monkeypatch.setattr(action_module, "MAX_GITHUB_RESPONSE_BYTES", 16)
    client = GitHubClient(
        "token",
        "owner/repo",
        open_url=lambda *_args, **_kwargs: Response(b"x" * 17),
    )

    with pytest.raises(ActionError, match="safe size limit"):
        client.read_pull_request(8)


def test_evidence_responses_share_one_total_byte_budget():
    client = GitHubClient(
        "token",
        "owner/repo",
        open_url=lambda *_args, **_kwargs: Response(b"[]"),
    )
    budget = action_module._EvidenceBudget(limit=3)

    assert client._request("GET", "/one", budget=budget) == []
    with pytest.raises(ActionError, match="safe size limit"):
        client._request("GET", "/two", budget=budget)


def test_evidence_pagination_fails_closed_at_the_page_limit(monkeypatch):
    monkeypatch.setattr(action_module, "MAX_EVIDENCE_PAGES", 2)
    batch = [{"id": number} for number in range(100)]
    client = GitHubClient(
        "token",
        "owner/repo",
        open_url=lambda *_args, **_kwargs: Response(json.dumps(batch).encode()),
    )

    with pytest.raises(ActionError, match="too many pages"):
        client._list_all("/items", action_module._EvidenceBudget())


def test_marker_search_fails_closed_instead_of_creating_after_page_cap(monkeypatch):
    monkeypatch.setattr(action_module, "MAX_EVIDENCE_PAGES", 2)
    requests = []
    comments = [
        {"id": number, "body": "human", "user": {"login": "person"}}
        for number in range(100)
    ]

    def open_url(request, timeout):
        requests.append(request)
        return Response(json.dumps(comments).encode())

    client = GitHubClient("token", "owner/repo", open_url=open_url)

    with pytest.raises(ActionError, match="comments have too many pages"):
        client.upsert_review_comment(8, "review")
    assert [request.method for request in requests] == ["GET", "GET"]
