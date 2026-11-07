"""Jira tool unit tests — F13FCAKE-9, F13FCAKE-10, F13FCAKE-18."""

import datetime
import httpx
import json
import yaml
import logging
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from connectonion.useful_tools.jira import (
    Jira,
    JiraAuthError,
    JiraConfigError,
    JiraPermissionError,
)

JIRA_URL = "https://test.atlassian.net"
JIRA_EMAIL = "test@example.com"
JIRA_TOKEN = "test-api-token-do-not-log"

@pytest.fixture(autouse=True)
def jira_env(monkeypatch):
    """Provide valid Jira env vars for every test; use monkeypatch for per-test overrides."""
    monkeypatch.setenv("JIRA_URL", JIRA_URL)
    monkeypatch.setenv("JIRA_EMAIL", JIRA_EMAIL)
    monkeypatch.setenv("JIRA_API_TOKEN", JIRA_TOKEN)

def _mock_get(routes: dict):
    """
    Return (get_fn, calls) where get_fn is a drop-in for httpx.get.

    routes: {url_suffix: (http_status, json_body)}
    url_suffix is matched against url after stripping query-string.
    calls: list of {"url": ..., "params": ...} appended on each invocation.
    """
    calls: list[dict] = []

    def get(url, auth=None, params=None, timeout=None):
        calls.append({"url": url, "params": dict(params or {})})
        for suffix, (status, body) in routes.items():
            if url.rstrip("/").endswith(suffix):
                resp = MagicMock(status_code=status)
                resp.json = MagicMock(return_value=body)
                resp.raise_for_status = MagicMock()
                return resp
        raise AssertionError(f"Unexpected GET {url!r} params={params!r}")

    return get, calls

_P1 = {"key": "ALPHA", "name": "Alpha Project"}
_P2 = {"key": "BETA", "name": "Beta Project"}
_P3 = {"key": "GAMMA", "name": "Gamma Project"}

_I1 = {"id": "10001", "key": "ALPHA-1", "fields": {"summary": "First issue"}}
_I2 = {"id": "10002", "key": "ALPHA-2", "fields": {"summary": "Second issue"}}
_I3 = {"id": "10003", "key": "ALPHA-3", "fields": {"summary": "Third issue"}}

def test_project_items_follows_pagination_two_pages():
    """10-2: two pages → combined list; exactly two HTTP requests."""
    call_seq = [0]

    def get(url, auth=None, params=None, timeout=None):
        call_seq[0] += 1
        resp = MagicMock(status_code=200)
        resp.raise_for_status = MagicMock()
        if call_seq[0] == 1:
            resp.json = MagicMock(return_value={"values": [_P1, _P2], "isLast": False})
        else:
            resp.json = MagicMock(return_value={"values": [_P3], "isLast": True})
        return resp

    with patch("connectonion.useful_tools.jira.httpx.get", get):
        result = Jira().project_items()

    assert result == [_P1, _P2, _P3]
    assert call_seq[0] == 2

def test_project_items_second_page_startAt_equals_first_page_length():
    """10-3: second request startAt equals the number of items on page 1."""
    received: list[dict] = []

    def get(url, auth=None, params=None, timeout=None):
        received.append(dict(params or {}))
        resp = MagicMock(status_code=200)
        resp.raise_for_status = MagicMock()
        if len(received) == 1:
            resp.json = MagicMock(return_value={"values": [_P1, _P2], "isLast": False})
        else:
            resp.json = MagicMock(return_value={"values": [_P3], "isLast": True})
        return resp

    with patch("connectonion.useful_tools.jira.httpx.get", get):
        Jira().project_items()

    assert len(received) == 2
    assert received[1].get("startAt") == 2

def test_project_items_single_page_sends_exactly_one_request():
    """10-4: isLast=true on the only page → exactly one HTTP request."""
    get, calls = _mock_get(
        {"/rest/api/3/project/search": (200, {"values": [_P1], "isLast": True})}
    )

    with patch("connectonion.useful_tools.jira.httpx.get", get):
        result = Jira().project_items()

    assert result == [_P1]
    assert len(calls) == 1

@pytest.mark.parametrize("body", [
    {}, {"values": None, "isLast": True}, {"values": [], "isLast": "false"},
    {"values": [{"name": "Missing key"}], "isLast": True},
    {"values": [{"key": "ALPHA", "name": None}], "isLast": True},
    {"values": [_P1], "isLast": True, "warningMessages": ["Partial results"]},
])
def test_project_listing_refuses_malformed_or_incomplete_provider_data(body):
    with patch.object(Jira, "_get", return_value=body):
        with pytest.raises(ValueError, match="malformed|incomplete"):
            Jira().project_items()

@pytest.mark.parametrize("body", [
    {"issues": [_I1], "warningMessages": ["Partial query result"]},
    {"issues": [_I1], "errorMessages": ["Query failed"]},
    {"issues": [_I1], "errors": {"query": "invalid"}},
    {},
])
def test_selected_issue_read_does_not_accept_query_warnings_or_missing_data(body):
    with patch.object(Jira, "_get", return_value=body):
        with pytest.raises(ValueError, match="incomplete|malformed"):
            Jira().issue_items("ALPHA", {"ALPHA-1"})

def test_project_items_stops_safely_on_non_progressing_page():
    """10-4b: values=[] + isLast=false → raises ValueError; HTTP calls bounded."""
    call_count = [0]

    def get(url, auth=None, params=None, timeout=None):
        call_count[0] += 1
        resp = MagicMock(status_code=200)
        resp.raise_for_status = MagicMock()
        resp.json = MagicMock(return_value={"values": [], "isLast": False})
        return resp

    with patch("connectonion.useful_tools.jira.httpx.get", get):
        with pytest.raises(ValueError, match="empty page"):
            Jira().project_items()

    assert call_count[0] <= 5

def test_issue_items_stops_safely_on_repeated_next_page_token():
    """10-4c: non-progressing cursor → raises ValueError; HTTP calls bounded.

    Also verifies that the cursor is correctly echoed back to Jira on each
    subsequent request (params["nextPageToken"] == FIXED_TOKEN on call 2+).
    """
    FIXED_TOKEN = "cursor-that-never-advances"
    received_params: list[dict] = []

    def get(url, auth=None, params=None, timeout=None):
        received_params.append(dict(params or {}))
        resp = MagicMock(status_code=200)
        resp.raise_for_status = MagicMock()
        resp.json = MagicMock(return_value={
            "issues": [_I1],
            "nextPageToken": FIXED_TOKEN,
        })
        return resp

    with patch("connectonion.useful_tools.jira.httpx.get", get):
        with pytest.raises(ValueError, match="cursor did not advance"):
            Jira().issue_items("ALPHA", {"ALPHA-1"})

    assert len(received_params) <= 5

    assert received_params[1].get("nextPageToken") == FIXED_TOKEN

def test_valid_credentials_identify_authorized_site_without_persisting_token():
    """9-0: verify_connection() returns accountId + site_url; token absent from result and disk."""
    get, _ = _mock_get({"/rest/api/3/myself": (200, {"accountId": "abc123", "displayName": "Alice"})})

    with patch("connectonion.useful_tools.jira.httpx.get", get):
        result = Jira().verify_connection()

    assert result["accountId"] == "abc123"
    assert result["site_url"] == JIRA_URL
    for v in result.values():
        assert JIRA_TOKEN not in str(v)

    for f in Path.home().rglob("*"):
        if f.is_file():
            assert JIRA_TOKEN not in f.read_text(encoding="utf-8", errors="ignore")


def test_missing_jira_url_raises_config_error(monkeypatch):
    """9-1: all three vars absent → JiraConfigError naming JIRA_URL with repair hint."""
    monkeypatch.delenv("JIRA_URL")
    monkeypatch.delenv("JIRA_EMAIL")
    monkeypatch.delenv("JIRA_API_TOKEN")
    with pytest.raises(JiraConfigError, match="JIRA_URL") as exc_info:
        Jira()
    assert "co env set JIRA_URL" in str(exc_info.value)


def test_missing_email_raises_config_error(monkeypatch):
    """9-2: JIRA_URL set, JIRA_EMAIL absent → JiraConfigError naming JIRA_EMAIL."""
    monkeypatch.delenv("JIRA_EMAIL")
    with pytest.raises(JiraConfigError, match="JIRA_EMAIL"):
        Jira()


def test_missing_token_raises_config_error(monkeypatch):
    """9-3: JIRA_URL + JIRA_EMAIL set, JIRA_API_TOKEN absent → JiraConfigError naming JIRA_API_TOKEN."""
    monkeypatch.delenv("JIRA_API_TOKEN")
    with pytest.raises(JiraConfigError, match="JIRA_API_TOKEN"):
        Jira()


def test_invalid_credentials_raise_auth_error_with_standard_message():
    """9-4: 401 → JiraAuthError; message contains 'Jira authentication failed'; no speculation."""
    get, _ = _mock_get({"/rest/api/3/myself": (401, {})})

    with patch("connectonion.useful_tools.jira.httpx.get", get):
        with pytest.raises(JiraAuthError) as exc_info:
            Jira().verify_connection()

    msg = str(exc_info.value)
    assert "Jira authentication failed" in msg
    assert "expired" not in msg
    assert "invalid token" not in msg
    assert "过期" not in msg


def test_401_message_does_not_speculate_about_cause():
    """9-5: same 401 path; no speculation words; repair hint present."""
    get, _ = _mock_get({"/rest/api/3/myself": (401, {})})

    with patch("connectonion.useful_tools.jira.httpx.get", get):
        with pytest.raises(JiraAuthError) as exc_info:
            Jira().verify_connection()

    msg = str(exc_info.value)
    assert "expired" not in msg
    assert "invalid token" not in msg
    assert "export JIRA_API_TOKEN" in msg


def test_no_records_written_when_auth_fails(caplog):
    """9-6: 401 via project_items() → no .jsonl/.yaml under HOME; token absent from all logs."""
    get, _ = _mock_get({"/rest/api/3/project/search": (401, {})})

    with caplog.at_level(logging.NOTSET):
        with patch("connectonion.useful_tools.jira.httpx.get", get):
            with pytest.raises(JiraAuthError):
                Jira().project_items()

    home = Path.home()
    assert list(home.rglob("*.jsonl")) == []
    assert list(home.rglob("*.yaml")) == []

    for record in caplog.records:
        assert JIRA_TOKEN not in record.getMessage()


def test_network_timeout_raises_recoverable_value_error_with_retry_hint():
    """9-7: httpx.TimeoutException → ValueError (not JiraAuthError/JiraPermissionError); message has retry hint."""
    def get(url, auth=None, params=None, timeout=None):
        raise httpx.TimeoutException('timed out', request=None)

    with patch('connectonion.useful_tools.jira.httpx.get', get):
        with pytest.raises(ValueError) as exc_info:
            Jira().project_items()

    assert not isinstance(exc_info.value, JiraAuthError)
    assert not isinstance(exc_info.value, JiraPermissionError)
    msg = str(exc_info.value)
    assert 'try again' in msg.lower() or 'retry' in msg.lower() or 'timed out' in msg.lower()


def test_no_mutating_requests_sent():
    """9-8: no PUT/PATCH/DELETE ever; no POST to mutation endpoints.

    POST is not blanket-banned: future read-only queries via POST (e.g. /search/jql)
    are allowed.  Only POSTs that mutate Jira data (/issue, /comment, /transition,
    /edit, /create) are forbidden.
    """
    _MUTATION_FRAGMENTS = ("/issue", "/comment", "/transition", "/edit", "/create")

    get, _ = _mock_get({
        '/rest/api/3/project/search': (200, {'values': [_P1], 'isLast': True}),
        '/rest/api/3/search/jql': (200, {'issues': [_I1]}),
    })

    post_urls: list[str] = []

    def _record_post(url, **kwargs):
        post_urls.append(url)
        resp = MagicMock(status_code=200)
        resp.json = MagicMock(return_value={})
        resp.raise_for_status = MagicMock()
        return resp

    with (
        patch('connectonion.useful_tools.jira.httpx.get', get),
        patch('connectonion.useful_tools.jira.httpx.post', _record_post),
        patch('connectonion.useful_tools.jira.httpx.put') as mock_put,
        patch('connectonion.useful_tools.jira.httpx.patch') as mock_patch,
        patch('connectonion.useful_tools.jira.httpx.delete') as mock_delete,
    ):
        j = Jira()
        j.project_items()
        j.issue_items('ALPHA', {'ALPHA-1'})

    mock_put.assert_not_called()
    mock_patch.assert_not_called()
    mock_delete.assert_not_called()
    for url in post_urls:
        for fragment in _MUTATION_FRAGMENTS:
            assert fragment not in url, f"POST to mutation endpoint detected: {url!r}"


def test_rate_limit_returns_recoverable_error_or_bounded_retry():
    """9-9: HTTP 429 → ValueError with rate-limit message; never returns []; HTTP calls bounded (≤ 5)."""
    call_count = [0]

    def get(url, auth=None, params=None, timeout=None):
        call_count[0] += 1
        resp = MagicMock(status_code=429)
        resp.json = MagicMock(return_value={})
        resp.raise_for_status = MagicMock()
        return resp

    with patch('connectonion.useful_tools.jira.httpx.get', get):
        with pytest.raises(ValueError) as exc_info:
            Jira().project_items()

    assert call_count[0] <= 5
    msg = str(exc_info.value)
    assert '429' in msg or 'rate limit' in msg.lower() or 'rate-limit' in msg.lower()

# ── STEP 4 TESTS (10-1, 10-5 through 10-15) ──

def test_project_items_return_type_is_list_of_dict():
    """10-1: project_items() returns list[dict]; each dict contains 'key' and 'name'."""
    get, _ = _mock_get(
        {"/rest/api/3/project/search": (200, {"values": [_P1, _P2], "isLast": True})}
    )
    with patch("connectonion.useful_tools.jira.httpx.get", get):
        result = Jira().project_items()
    assert isinstance(result, list)
    for item in result:
        assert isinstance(item, dict)
        assert "key" in item
        assert "name" in item


def test_project_items_valid_empty_result_returns_empty_list():
    """10-5: values=[] + isLast=true -> returns []; no exception raised."""
    get, _ = _mock_get(
        {"/rest/api/3/project/search": (200, {"values": [], "isLast": True})}
    )
    with patch("connectonion.useful_tools.jira.httpx.get", get):
        result = Jira().project_items()
    assert result == []


def test_issue_items_raises_before_network_when_no_issue_keys_selected():
    """10-6: empty selected_issue_keys -> ValueError before any HTTP request (count == 0)."""
    call_count = [0]

    def get(url, **kwargs):
        call_count[0] += 1
        raise AssertionError("HTTP should not be called for empty key set")

    with patch("connectonion.useful_tools.jira.httpx.get", get):
        with pytest.raises(ValueError, match="non-empty"):
            Jira().issue_items("ALPHA", set())
    assert call_count[0] == 0


def test_issue_items_rejects_unknown_project_key_before_collection():
    """10-6b: project not in accessible_keys -> ValueError, 0 HTTP requests."""
    call_count = [0]

    def get(url, **kwargs):
        call_count[0] += 1
        raise AssertionError("HTTP should not be called when project not accessible")

    with patch("connectonion.useful_tools.jira.httpx.get", get):
        with pytest.raises(ValueError):
            Jira().issue_items(
                "GAMMA", {"GAMMA-1"},
                accessible_keys={"ALPHA", "BETA"},
            )
    assert call_count[0] == 0


def test_issue_items_jql_query_is_scoped_server_side_not_post_filtered():
    """10-6c: JQL sent to Jira scopes server-side: 'project = ALPHA AND key IN (...)'."""
    received_params: list[dict] = []

    def get(url, auth=None, params=None, timeout=None):
        received_params.append(dict(params or {}))
        resp = MagicMock(status_code=200)
        resp.raise_for_status = MagicMock()
        resp.json = MagicMock(return_value={"issues": [_I1, _I2]})
        return resp

    with patch("connectonion.useful_tools.jira.httpx.get", get):
        result = Jira().issue_items("ALPHA", {"ALPHA-1", "ALPHA-2"})

    assert len(received_params) == 1
    jql = received_params[0].get("jql", "")
    assert "project = ALPHA" in jql
    assert "ALPHA-1" in jql
    assert "ALPHA-2" in jql
    assert result == [_I1, _I2]


def test_issue_items_sends_explicit_fields_param():
    """10-6c-fields: issue_items() sends fields=<comma-list> to search/jql; contains required fields."""
    received_params: list[dict] = []

    def get(url, auth=None, params=None, timeout=None):
        received_params.append(dict(params or {}))
        resp = MagicMock(status_code=200)
        resp.raise_for_status = MagicMock()
        resp.json = MagicMock(return_value={"issues": [_I1]})
        return resp

    with patch("connectonion.useful_tools.jira.httpx.get", get):
        Jira().issue_items("ALPHA", {"ALPHA-1"})

    assert len(received_params) == 1
    fields_param = received_params[0].get("fields", "")
    assert fields_param, "fields param must be present and non-empty"
    field_names = [f.strip() for f in fields_param.split(",")]
    for required in ("summary", "description", "status", "created", "updated"):
        assert required in field_names, f"required field {required!r} missing from fields param"


def test_issue_items_realistic_response_shape_with_fields_succeeds():
    """10-6c-shape: server returns realistic shape (expand/fields/id/key/self) -> key check passes."""
    realistic_issue = {
        "expand": "operations,versionedRepresentations,editmeta,changelog,renderedFields",
        "id": "10001",
        "key": "ALPHA-1",
        "self": "https://example.atlassian.net/rest/api/3/issue/10001",
        "fields": {
            "summary": "Realistic issue summary",
            "description": None,
            "status": {"name": "To Do", "id": "1"},
            "created": "2024-01-15T09:00:00.000+0000",
            "updated": "2024-01-16T12:00:00.000+0000",
        },
    }

    def get(url, auth=None, params=None, timeout=None):
        resp = MagicMock(status_code=200)
        resp.raise_for_status = MagicMock()
        resp.json = MagicMock(return_value={"issues": [realistic_issue]})
        return resp

    with patch("connectonion.useful_tools.jira.httpx.get", get):
        result = Jira().issue_items("ALPHA", {"ALPHA-1"})

    assert len(result) == 1
    assert result[0]["key"] == "ALPHA-1"
    assert result[0]["fields"]["summary"] == "Realistic issue summary"


def test_issue_items_rejects_key_from_wrong_project_before_network():
    """10-6d: BETA-1 passed to ALPHA project -> ValueError, 0 HTTP; message names the key."""
    call_count = [0]

    def get(url, **kwargs):
        call_count[0] += 1
        raise AssertionError("HTTP should not be called for mismatched project key")

    with patch("connectonion.useful_tools.jira.httpx.get", get):
        with pytest.raises(ValueError) as exc_info:
            Jira().issue_items("ALPHA", {"BETA-1"})
    assert call_count[0] == 0
    assert "BETA-1" in str(exc_info.value)


def test_issue_items_rejects_malicious_key_to_prevent_jql_injection():
    """10-6e: keys with quotes/spaces/AND -> ValueError, 0 HTTP requests each."""
    malicious = [
        {"ALPHA-1' OR project = EVIL"},
        {"ALPHA 1"},
        {"ALPHA-1 AND project=EVIL"},
    ]
    for key_set in malicious:
        count = [0]

        def _track(url, **kwargs):
            count[0] += 1
            raise AssertionError(f"HTTP called for malicious key {key_set!r}")

        with patch("connectonion.useful_tools.jira.httpx.get", _track):
            with pytest.raises(ValueError):
                Jira().issue_items("ALPHA", key_set)
        assert count[0] == 0, f"HTTP was called for {key_set!r}"


def test_issue_items_raises_permission_error_on_403_with_safe_message():
    """10-7: HTTP 403 -> JiraPermissionError; message contains project key; no server body."""
    get, _ = _mock_get(
        {"/rest/api/3/search/jql": (403, {"errorMessages": ["Access denied"]})}
    )
    with patch("connectonion.useful_tools.jira.httpx.get", get):
        with pytest.raises(JiraPermissionError) as exc_info:
            Jira().issue_items("ALPHA", {"ALPHA-1"})
    msg = str(exc_info.value)
    assert "ALPHA" in msg
    assert "Access denied" not in msg
    assert "errorMessages" not in msg


def test_issue_items_pagination_collects_all_pages_via_confirmed_cursor():
    """10-8: two-page nextPageToken cursor -> all issues combined; 2 HTTP requests."""
    call_seq = [0]

    def get(url, auth=None, params=None, timeout=None):
        call_seq[0] += 1
        resp = MagicMock(status_code=200)
        resp.raise_for_status = MagicMock()
        if call_seq[0] == 1:
            resp.json = MagicMock(return_value={
                "issues": [_I1, _I2],
                "nextPageToken": "page-2-token",
            })
        else:
            resp.json = MagicMock(return_value={"issues": [_I3]})
        return resp

    with patch("connectonion.useful_tools.jira.httpx.get", get):
        result = Jira().issue_items("ALPHA", {"ALPHA-1", "ALPHA-2", "ALPHA-3"})

    assert result == [_I1, _I2, _I3]
    assert call_seq[0] == 2


def test_issue_items_raises_when_all_requested_keys_missing():
    """10-9: issues=[] when keys are requested -> ValueError naming missing keys."""
    get, _ = _mock_get(
        {"/rest/api/3/search/jql": (200, {"issues": []})}
    )
    with patch("connectonion.useful_tools.jira.httpx.get", get):
        with pytest.raises(ValueError, match="ALPHA-1"):
            Jira().issue_items("ALPHA", {"ALPHA-1"})
