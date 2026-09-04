"""Tests for YoucomSearch tool integration."""

import json
import os
import pytest
from unittest.mock import patch, Mock, MagicMock

from connectonion.useful_tools.youcom_search import YoucomSearch

import httpx as _real_httpx


def _patched_httpx():
    """Patch httpx in the module but keep real exception classes so the
    module's `except httpx.HTTPStatusError` clauses work."""
    patcher = patch('connectonion.useful_tools.youcom_search.httpx')
    mock_httpx = patcher.start()
    mock_httpx.HTTPStatusError = _real_httpx.HTTPStatusError
    mock_httpx.RequestError = _real_httpx.RequestError
    return patcher, mock_httpx


def test_youcom_search_init():
    """Test YoucomSearch initialization with default settings."""
    search = YoucomSearch()
    assert search.timeout == 30
    assert search.base_url == 'https://api.you.com'
    assert 'User-Agent' in search.headers
    assert search.headers['User-Agent'] == 'ConnectOnion/1.0 (Agent Framework)'


def test_youcom_search_init_with_api_key():
    """Test YoucomSearch initialization with API key."""
    with patch.dict(os.environ, {'YDC_API_KEY': 'test-key'}):
        search = YoucomSearch()
        assert 'Authorization' in search.headers
        assert search.headers['Authorization'] == 'Bearer test-key'


def test_youcom_search_init_custom_base_url():
    """Test YoucomSearch initialization with custom base URL."""
    with patch.dict(os.environ, {'YOUCOM_BASE_URL': 'https://custom.api.com'}):
        search = YoucomSearch()
        assert search.base_url == 'https://custom.api.com'


@patch('connectonion.useful_tools.youcom_search.httpx')
def test_search_success(mock_httpx):
    """Test successful search request."""
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.text = '{"results": ["test result"]}'
    mock_httpx.post.return_value = mock_response
    
    search = YoucomSearch()
    result = search.search("test query")
    
    assert result == '{"results": ["test result"]}'
    mock_httpx.post.assert_called_once()


@patch('connectonion.useful_tools.youcom_search.httpx')
def test_search_payment_required(mock_httpx):
    """Test search with 402 payment required response."""
    mock_response = Mock()
    mock_response.status_code = 402
    mock_httpx.post.return_value = mock_response
    
    search = YoucomSearch()
    result = search.search("test query")
    
    result_data = json.loads(result)
    assert result_data['error'] == 'payment_required'
    assert 'x402-aware' in result_data['message']


@patch('connectonion.useful_tools.youcom_search.httpx')
def test_search_auth_failure_with_fallback(mock_httpx):
    """Test search with authentication failure and free search fallback."""
    mock_httpx.HTTPStatusError = _real_httpx.HTTPStatusError
    mock_httpx.RequestError = _real_httpx.RequestError

    # First call (authenticated) fails with 401
    mock_response_auth = Mock()
    mock_response_auth.status_code = 401
    mock_response_auth.text = "Unauthorized"
    mock_response_auth.raise_for_status.side_effect = _real_httpx.HTTPStatusError(
        "401 Unauthorized", request=Mock(), response=mock_response_auth
    )

    # Second call (free search) succeeds
    mock_response_free = Mock()
    mock_response_free.status_code = 200
    mock_response_free.text = '{"results": ["free result"]}'
    mock_response_free.raise_for_status.return_value = None

    mock_httpx.post.side_effect = [mock_response_auth, mock_response_free]

    with patch.dict(os.environ, {'YDC_API_KEY': 'invalid-key'}):
        search = YoucomSearch()
        result = search.search("test query")

    result_data = json.loads(result)
    assert "_fallback_notice" in result_data
    assert "free search" in result_data["_fallback_notice"]


@patch('connectonion.useful_tools.youcom_search.httpx')
def test_get_contents_success(mock_httpx):
    """Test successful content extraction."""
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.text = '{"contents": [{"url": "test.com", "text": "content"}]}'
    mock_httpx.post.return_value = mock_response
    
    search = YoucomSearch()
    result = search.get_contents("https://test.com")
    
    assert result == '{"contents": [{"url": "test.com", "text": "content"}]}'


@patch('connectonion.useful_tools.youcom_search.httpx')
def test_get_contents_auth_required(mock_httpx):
    """Test content extraction requiring authentication."""
    mock_httpx.HTTPStatusError = _real_httpx.HTTPStatusError
    mock_httpx.RequestError = _real_httpx.RequestError

    mock_response = Mock()
    mock_response.status_code = 401
    mock_response.text = "Unauthorized"
    mock_httpx.post.return_value = mock_response
    mock_response.raise_for_status.side_effect = _real_httpx.HTTPStatusError(
        "401", request=Mock(), response=mock_response
    )

    search = YoucomSearch()
    result = search.get_contents("https://test.com")

    result_data = json.loads(result)
    assert result_data['error'] == 'auth_required'
    assert 'YDC_API_KEY' in result_data['message']


def test_research_no_api_key():
    """Test research method without API key."""
    search = YoucomSearch()
    result = search.research("test query")
    
    result_data = json.loads(result)
    assert result_data['error'] == 'auth_required'
    assert 'YDC_API_KEY' in result_data['message']


@patch('connectonion.useful_tools.youcom_search.httpx')
def test_research_success(mock_httpx):
    """Test successful research synthesis."""
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.text = '{"synthesis": "research result", "citations": []}'
    mock_httpx.post.return_value = mock_response
    
    with patch.dict(os.environ, {'YDC_API_KEY': 'test-key'}):
        search = YoucomSearch()
        result = search.research("test query")
    
    assert result == '{"synthesis": "research result", "citations": []}'


def test_search_parameter_limits():
    """Test search parameter validation and limits."""
    search = YoucomSearch()
    
    # Test count limits
    with patch('connectonion.useful_tools.youcom_search.httpx') as mock_httpx:
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.text = '{}'
        mock_httpx.post.return_value = mock_response
        
        search.search("test", count=25)  # Should be capped at 20
        call_args = mock_httpx.post.call_args[1]['json']
        assert call_args['count'] == 20
        
        search.search("test", count=0)  # Should be raised to 1
        call_args = mock_httpx.post.call_args[1]['json']
        assert call_args['count'] == 1


def test_get_contents_url_handling():
    """Test URL handling in get_contents method."""
    search = YoucomSearch()
    
    with patch('connectonion.useful_tools.youcom_search.httpx') as mock_httpx:
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.text = '{}'
        mock_httpx.post.return_value = mock_response
        
        # Test single URL string
        search.get_contents("https://test.com")
        call_args = mock_httpx.post.call_args[1]['json']
        assert call_args['urls'] == ["https://test.com"]
        
        # Test URL list
        urls = ["https://test1.com", "https://test2.com"]
        search.get_contents(urls)
        call_args = mock_httpx.post.call_args[1]['json']
        assert call_args['urls'] == urls
        
        # Test URL limit (max 10)
        many_urls = [f"https://test{i}.com" for i in range(15)]
        search.get_contents(many_urls)
        call_args = mock_httpx.post.call_args[1]['json']
        assert len(call_args['urls']) == 10


def test_network_error_handling():
    """Test network error handling."""
    patcher, mock_httpx = _patched_httpx()
    try:
        mock_httpx.post.side_effect = Exception("Network timeout")

        search = YoucomSearch()
        result = search.search("test query")

        result_data = json.loads(result)
        assert result_data['error'] == 'network_error'
        assert 'Network timeout' in result_data['message']
    finally:
        patcher.stop()
