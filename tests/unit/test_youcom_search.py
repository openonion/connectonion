"""Tests for the You.com function tools."""

from unittest.mock import Mock, patch

import httpx as _real_httpx

from connectonion.useful_tools.youcom_search import (
    youcom_contents,
    youcom_research,
    youcom_search,
)

MODULE = "connectonion.useful_tools.youcom_search"


def _mock_httpx():
    """Patch httpx in the module but keep the real exception classes so the
    module's `except httpx.RequestError` clause works."""
    patcher = patch(f"{MODULE}.httpx")
    mock_httpx = patcher.start()
    mock_httpx.RequestError = _real_httpx.RequestError
    return patcher, mock_httpx


def _response(status_code=200, json_body=None, text=""):
    response = Mock()
    response.status_code = status_code
    response.is_error = status_code >= 400
    if json_body is not None:
        response.json.return_value = json_body
    else:
        response.json.side_effect = ValueError(text)
    return response


# --- no key: every tool returns the same auth_required shape ----------


def test_search_without_key(monkeypatch):
    monkeypatch.delenv("YDC_API_KEY", raising=False)
    result = youcom_search("anything")
    assert result["error"] == "auth_required"
    assert "YDC_API_KEY" in result["message"]


def test_contents_without_key(monkeypatch):
    monkeypatch.delenv("YDC_API_KEY", raising=False)
    result = youcom_contents("https://example.com")
    assert result["error"] == "auth_required"
    assert "YDC_API_KEY" in result["message"]


def test_research_without_key(monkeypatch):
    monkeypatch.delenv("YDC_API_KEY", raising=False)
    result = youcom_research("anything")
    assert result["error"] == "auth_required"
    assert "YDC_API_KEY" in result["message"]


# --- happy paths ------------------------------------------------------


def test_search_success(monkeypatch):
    monkeypatch.setenv("YDC_API_KEY", "test-key")
    patcher, mock_httpx = _mock_httpx()
    try:
        mock_httpx.post.return_value = _response(200, {"results": ["r"]})
        result = youcom_search("test query")
        assert result == {"results": ["r"]}
        args, kwargs = mock_httpx.post.call_args
        assert args[0] == "https://api.you.com/api/search"
        assert kwargs["json"]["query"] == "test query"
        assert kwargs["json"]["count"] == 10
        assert kwargs["headers"]["Authorization"] == "Bearer test-key"
    finally:
        patcher.stop()


def test_search_clamps_count(monkeypatch):
    monkeypatch.setenv("YDC_API_KEY", "test-key")
    patcher, mock_httpx = _mock_httpx()
    try:
        mock_httpx.post.return_value = _response(200, {})
        youcom_search("q", count=99)
        assert mock_httpx.post.call_args[1]["json"]["count"] == 20
        youcom_search("q", count=0)
        assert mock_httpx.post.call_args[1]["json"]["count"] == 1
    finally:
        patcher.stop()


def test_search_freshness_only_when_given(monkeypatch):
    monkeypatch.setenv("YDC_API_KEY", "test-key")
    patcher, mock_httpx = _mock_httpx()
    try:
        mock_httpx.post.return_value = _response(200, {})
        youcom_search("q")
        assert "freshness" not in mock_httpx.post.call_args[1]["json"]
        youcom_search("q", freshness="week")
        assert mock_httpx.post.call_args[1]["json"]["freshness"] == "week"
    finally:
        patcher.stop()


def test_search_reads_key_at_call_time(monkeypatch):
    """A key exported after import is picked up without any re-init."""
    monkeypatch.delenv("YDC_API_KEY", raising=False)
    patcher, mock_httpx = _mock_httpx()
    try:
        mock_httpx.post.return_value = _response(200, {})
        assert youcom_search("q")["error"] == "auth_required"
        mock_httpx.post.assert_not_called()
        monkeypatch.setenv("YDC_API_KEY", "late-key")
        assert youcom_search("q") == {}
        assert mock_httpx.post.call_args[1]["headers"]["Authorization"] == "Bearer late-key"
    finally:
        patcher.stop()


def test_contents_success_single_url_and_cap(monkeypatch):
    monkeypatch.setenv("YDC_API_KEY", "test-key")
    patcher, mock_httpx = _mock_httpx()
    try:
        mock_httpx.post.return_value = _response(200, {"contents": []})
        youcom_contents("https://test.com")
        assert mock_httpx.post.call_args[1]["json"]["urls"] == ["https://test.com"]
        many = [f"https://t{i}.com" for i in range(15)]
        youcom_contents(many)
        assert len(mock_httpx.post.call_args[1]["json"]["urls"]) == 10
    finally:
        patcher.stop()


def test_research_success(monkeypatch):
    monkeypatch.setenv("YDC_API_KEY", "test-key")
    patcher, mock_httpx = _mock_httpx()
    try:
        mock_httpx.post.return_value = _response(200, {"synthesis": "s", "citations": []})
        result = youcom_research("test query")
        assert result["synthesis"] == "s"
        assert mock_httpx.post.call_args[0][0] == "https://api.you.com/api/research"
    finally:
        patcher.stop()


# --- failure translation ----------------------------------------------


def test_search_payment_required(monkeypatch):
    monkeypatch.setenv("YDC_API_KEY", "test-key")
    patcher, mock_httpx = _mock_httpx()
    try:
        mock_httpx.post.return_value = _response(402)
        result = youcom_search("q")
        assert result["error"] == "payment_required"
    finally:
        patcher.stop()


def test_search_rejected_credentials(monkeypatch):
    monkeypatch.setenv("YDC_API_KEY", "bad-key")
    patcher, mock_httpx = _mock_httpx()
    try:
        mock_httpx.post.return_value = _response(401)
        result = youcom_search("q")
        assert result["error"] == "auth_required"
    finally:
        patcher.stop()


def test_contents_http_error(monkeypatch):
    monkeypatch.setenv("YDC_API_KEY", "test-key")
    patcher, mock_httpx = _mock_httpx()
    try:
        mock_httpx.post.return_value = _response(500)
        result = youcom_contents(["https://test.com"])
        assert result["error"] == "contents_failed"
        assert "500" in result["message"]
    finally:
        patcher.stop()


def test_network_error_names_class_not_url(monkeypatch):
    monkeypatch.setenv("YDC_API_KEY", "test-key")
    patcher, mock_httpx = _mock_httpx()
    try:
        mock_httpx.post.side_effect = _real_httpx.ConnectTimeout("boom https://api.you.com")
        result = youcom_search("q")
        assert result["error"] == "network_error"
        # The class name, not the URL (or anything in it), reaches the agent.
        assert "ConnectTimeout" in result["message"]
        assert "you.com" not in result["message"]
    finally:
        patcher.stop()


def test_non_dict_json_body(monkeypatch):
    monkeypatch.setenv("YDC_API_KEY", "test-key")
    patcher, mock_httpx = _mock_httpx()
    try:
        mock_httpx.post.return_value = _response(200, ["not", "a", "dict"])
        result = youcom_search("q")
        assert result["error"] == "search_failed"
    finally:
        patcher.stop()


def test_200_without_json(monkeypatch):
    monkeypatch.setenv("YDC_API_KEY", "test-key")
    patcher, mock_httpx = _mock_httpx()
    try:
        mock_httpx.post.return_value = _response(200, None)
        result = youcom_research("q")
        assert result["error"] == "research_failed"
    finally:
        patcher.stop()
