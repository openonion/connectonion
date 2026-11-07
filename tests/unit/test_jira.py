import json

import httpx
import pytest

from connectonion.useful_tools import jira as jira_module
from connectonion.useful_tools.jira import Jira, JiraAuthError, JiraConfigError


class Response:
    def __init__(self, status_code, body):
        self.status_code, self._body = status_code, body

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("bad", request=None, response=None)

    def json(self):
        return self._body


@pytest.fixture
def configured(monkeypatch):
    values = {"JIRA_URL": "https://example.atlassian.net", "JIRA_EMAIL": "person@example.test", "JIRA_API_TOKEN": "token-value-123"}
    monkeypatch.setattr(jira_module, "setting", values.get)
    return values


def test_missing_token_has_safe_repair_guidance(monkeypatch):
    monkeypatch.setattr(jira_module, "setting", lambda name: {"JIRA_URL": "https://example.atlassian.net", "JIRA_EMAIL": "person@example.test"}.get(name))
    with pytest.raises(JiraConfigError, match="JIRA_API_TOKEN"):
        Jira()


def test_verify_does_not_return_token(configured, monkeypatch):
    monkeypatch.setattr(jira_module.httpx, "get", lambda *args, **kwargs: Response(200, {"accountId": "a1", "displayName": "Ada"}))
    result = Jira().verify_connection()
    assert result == {"accountId": "a1", "displayName": "Ada", "site_url": "https://example.atlassian.net"}
    assert "token-value-123" not in json.dumps(result)


def test_projects_follow_pagination(configured, monkeypatch):
    pages = iter([Response(200, {"values": [{"key": "A", "name": "Alpha"}], "isLast": False}), Response(200, {"values": [{"key": "B", "name": "Beta"}], "isLast": True})])
    monkeypatch.setattr(jira_module.httpx, "get", lambda *args, **kwargs: next(pages))
    assert [item["key"] for item in Jira().project_items()] == ["A", "B"]


def test_issue_selection_is_server_scoped_and_rejects_wrong_prefix(configured, monkeypatch):
    calls = []
    monkeypatch.setattr(jira_module.httpx, "get", lambda *args, **kwargs: calls.append(kwargs) or Response(200, {"issues": [{"key": "ALPHA-1", "fields": {}}]}))
    assert Jira().issue_items("ALPHA", {"ALPHA-1"})[0]["key"] == "ALPHA-1"
    assert calls[0]["params"]["jql"] == "project = ALPHA AND key IN (ALPHA-1)"
    with pytest.raises(ValueError):
        Jira().issue_items("ALPHA", {"BETA-1"})


def test_401_is_typed_and_safe(configured, monkeypatch):
    monkeypatch.setattr(jira_module.httpx, "get", lambda *args, **kwargs: Response(401, {}))
    with pytest.raises(JiraAuthError, match="authentication failed") as error:
        Jira().verify_connection()
    assert "token-value-123" not in str(error.value)


def test_source_yaml_refuses_to_replace_a_different_scope(configured, tmp_path):
    jira = Jira()
    jira.write_source_yaml(tmp_path, "ALPHA", {"ALPHA-1"})
    with pytest.raises(ValueError, match="different Jira account or selected scope"):
        jira.write_source_yaml(tmp_path, "ALPHA", {"ALPHA-2"})
