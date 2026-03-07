"""Unit tests for connectonion/useful_tools/gatheris.py

Tests cover:
- GatherIs initialization and configuration
- browse_feed: public feed retrieval
- discover_agents: agent listing
- post: authenticated posting with PoW
- comment: authenticated commenting
- _authenticate: Ed25519 challenge-response flow
- _solve_pow: hashcash proof-of-work solving
"""

import pytest
import base64
import hashlib
from unittest.mock import Mock, patch, MagicMock

from connectonion.useful_tools.gatheris import GatherIs, _load_ed25519_key, _PKCS8_ED25519_PREFIX


SAMPLE_FEED_RESPONSE = {
    "posts": [
        {
            "id": "post-1",
            "title": "Test Post",
            "summary": "A test post about agents",
            "author": "test-agent",
            "score": 5,
            "comment_count": 2,
            "tags": ["agents", "test"],
            "created": "2026-02-13T12:00:00Z",
        },
        {
            "id": "post-2",
            "title": "Another Post",
            "summary": "Another post",
            "author": "other-agent",
            "score": 3,
            "comment_count": 0,
            "tags": ["discussion"],
            "created": "2026-02-13T11:00:00Z",
        },
    ],
    "total": 2,
}

SAMPLE_AGENTS_RESPONSE = {
    "agents": [
        {
            "agent_id": "agent-1",
            "name": "test-agent",
            "verified": True,
            "post_count": 10,
            "created": "2026-01-01",
        },
        {
            "agent_id": "agent-2",
            "name": "other-agent",
            "verified": False,
            "post_count": 3,
            "created": "2026-02-01",
        },
    ],
    "total": 2,
}


class TestGatherIsInit:
    """Tests for GatherIs initialization."""

    def test_default_base_url(self):
        """Test default base URL is gather.is."""
        gis = GatherIs()
        assert gis.base_url == "https://gather.is"

    def test_custom_base_url(self):
        """Test custom base URL."""
        gis = GatherIs(base_url="https://staging.gather.is")
        assert gis.base_url == "https://staging.gather.is"

    def test_base_url_strips_trailing_slash(self):
        """Test that trailing slash is removed from base URL."""
        gis = GatherIs(base_url="https://gather.is/")
        assert gis.base_url == "https://gather.is"

    def test_default_timeout(self):
        """Test default timeout is 15 seconds."""
        gis = GatherIs()
        assert gis.timeout == 15

    def test_custom_timeout(self):
        """Test custom timeout."""
        gis = GatherIs(timeout=30)
        assert gis.timeout == 30

    def test_no_signing_key_without_key_file(self):
        """Test that signing key is None when no key file exists."""
        gis = GatherIs(private_key_path="/nonexistent/path.pem")
        assert gis._signing_key is None

    @patch.dict("os.environ", {"GATHERIS_API_URL": "https://custom.gather.is"})
    def test_base_url_from_env(self):
        """Test base URL from environment variable."""
        gis = GatherIs()
        assert gis.base_url == "https://custom.gather.is"


class TestBrowseFeed:
    """Tests for browse_feed method."""

    @patch("connectonion.useful_tools.gatheris.requests.get")
    def test_browse_feed_success(self, mock_get):
        """Test successful feed retrieval."""
        mock_response = Mock()
        mock_response.json.return_value = SAMPLE_FEED_RESPONSE
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        gis = GatherIs()
        result = gis.browse_feed()

        assert "Test Post" in result
        assert "Another Post" in result
        assert "test-agent" in result
        assert "post-1" in result

    @patch("connectonion.useful_tools.gatheris.requests.get")
    def test_browse_feed_with_params(self, mock_get):
        """Test feed retrieval passes limit and sort."""
        mock_response = Mock()
        mock_response.json.return_value = SAMPLE_FEED_RESPONSE
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        gis = GatherIs()
        gis.browse_feed(limit=10, sort="hot")

        call_kwargs = mock_get.call_args
        assert call_kwargs[1]["params"]["limit"] == 10
        assert call_kwargs[1]["params"]["sort"] == "hot"

    @patch("connectonion.useful_tools.gatheris.requests.get")
    def test_browse_feed_caps_limit(self, mock_get):
        """Test that limit is capped at 50."""
        mock_response = Mock()
        mock_response.json.return_value = SAMPLE_FEED_RESPONSE
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        gis = GatherIs()
        gis.browse_feed(limit=100)

        call_kwargs = mock_get.call_args
        assert call_kwargs[1]["params"]["limit"] == 50

    @patch("connectonion.useful_tools.gatheris.requests.get")
    def test_browse_feed_empty(self, mock_get):
        """Test feed with no posts."""
        mock_response = Mock()
        mock_response.json.return_value = {"posts": []}
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        gis = GatherIs()
        result = gis.browse_feed()

        assert "No posts found" in result

    @patch("connectonion.useful_tools.gatheris.requests.get")
    def test_browse_feed_error(self, mock_get):
        """Test feed retrieval error handling."""
        mock_get.side_effect = Exception("Connection refused")

        gis = GatherIs()
        result = gis.browse_feed()

        assert "Error" in result


class TestDiscoverAgents:
    """Tests for discover_agents method."""

    @patch("connectonion.useful_tools.gatheris.requests.get")
    def test_discover_agents_success(self, mock_get):
        """Test successful agent discovery."""
        mock_response = Mock()
        mock_response.json.return_value = SAMPLE_AGENTS_RESPONSE
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        gis = GatherIs()
        result = gis.discover_agents()

        assert "test-agent" in result
        assert "[verified]" in result
        assert "other-agent" in result

    @patch("connectonion.useful_tools.gatheris.requests.get")
    def test_discover_agents_empty(self, mock_get):
        """Test empty agent list."""
        mock_response = Mock()
        mock_response.json.return_value = {"agents": []}
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        gis = GatherIs()
        result = gis.discover_agents()

        assert "No agents found" in result

    @patch("connectonion.useful_tools.gatheris.requests.get")
    def test_discover_agents_error(self, mock_get):
        """Test agent discovery error handling."""
        mock_get.side_effect = Exception("Timeout")

        gis = GatherIs()
        result = gis.discover_agents()

        assert "Error" in result


class TestPost:
    """Tests for post method."""

    def test_post_without_auth(self):
        """Test that post fails without authentication."""
        gis = GatherIs(private_key_path="/nonexistent.pem")
        result = gis.post("Title", "Summary", "Body", ["test"])

        assert "Error" in result
        assert "Not authenticated" in result

    @patch("connectonion.useful_tools.gatheris.requests.post")
    def test_post_success(self, mock_post):
        """Test successful post with mocked auth and PoW."""
        gis = GatherIs()
        gis._token = "test-token"  # Skip auth

        # Mock PoW challenge and post responses
        pow_response = Mock()
        pow_response.json.return_value = {"challenge": "abc", "difficulty": 1}
        pow_response.raise_for_status = Mock()

        post_response = Mock()
        post_response.json.return_value = {"id": "new-post-123"}
        post_response.raise_for_status = Mock()

        mock_post.side_effect = [pow_response, post_response]

        result = gis.post("Title", "Summary", "Body", ["test"])

        assert "Posted successfully" in result
        assert "new-post-123" in result


class TestComment:
    """Tests for comment method."""

    def test_comment_without_auth(self):
        """Test that comment fails without authentication."""
        gis = GatherIs(private_key_path="/nonexistent.pem")
        result = gis.comment("post-1", "Great post!")

        assert "Error" in result
        assert "Not authenticated" in result

    @patch("connectonion.useful_tools.gatheris.requests.post")
    def test_comment_success(self, mock_post):
        """Test successful comment with mocked auth."""
        gis = GatherIs()
        gis._token = "test-token"  # Skip auth

        mock_response = Mock()
        mock_response.raise_for_status = Mock()
        mock_post.return_value = mock_response

        result = gis.comment("post-1", "Great post!")

        assert "Comment added" in result
        assert "post-1" in result


class TestAuthenticate:
    """Tests for _authenticate method."""

    def test_authenticate_returns_none_without_key(self):
        """Test that auth returns None without signing key."""
        gis = GatherIs(private_key_path="/nonexistent.pem")
        assert gis._authenticate() is None

    def test_authenticate_returns_cached_token(self):
        """Test that cached token is returned."""
        gis = GatherIs()
        gis._token = "cached-token"
        assert gis._authenticate() == "cached-token"


class TestSolvePoW:
    """Tests for _solve_pow method."""

    @patch("connectonion.useful_tools.gatheris.requests.post")
    def test_solve_pow_finds_solution(self, mock_post):
        """Test that PoW solver finds a valid nonce."""
        # Use difficulty=1 (very easy) for fast test
        mock_response = Mock()
        mock_response.json.return_value = {
            "challenge": "test-challenge",
            "difficulty": 1,
        }
        mock_response.raise_for_status = Mock()
        mock_post.return_value = mock_response

        gis = GatherIs()
        result = gis._solve_pow()

        assert result is not None
        assert "pow_challenge" in result
        assert "pow_nonce" in result
        assert result["pow_challenge"] == "test-challenge"

        # Verify the solution is actually valid
        nonce = result["pow_nonce"]
        hash_bytes = hashlib.sha256(
            f"test-challenge:{nonce}".encode()
        ).digest()
        first_bits = int.from_bytes(hash_bytes[:4], "big")
        assert first_bits >> 31 == 0  # difficulty=1 means 1 leading zero bit

    @patch("connectonion.useful_tools.gatheris.requests.post")
    def test_solve_pow_error(self, mock_post):
        """Test PoW solver handles errors."""
        mock_post.side_effect = Exception("Connection refused")

        gis = GatherIs()
        result = gis._solve_pow()

        assert result is None


class TestLoadEd25519Key:
    """Tests for _load_ed25519_key helper."""

    def test_load_nonexistent_file(self):
        """Test loading from nonexistent file returns None."""
        assert _load_ed25519_key("/nonexistent/path.pem") is None

    def test_load_valid_pem(self, tmp_path):
        """Test loading a valid Ed25519 PEM key."""
        # Create a valid PKCS8 Ed25519 PEM (48 bytes DER)
        raw_key = b"\x01" * 32  # Dummy 32-byte key
        der = _PKCS8_ED25519_PREFIX + raw_key
        b64 = base64.b64encode(der).decode()
        pem = f"-----BEGIN PRIVATE KEY-----\n{b64}\n-----END PRIVATE KEY-----"

        pem_file = tmp_path / "test_key.pem"
        pem_file.write_text(pem)

        result = _load_ed25519_key(str(pem_file))
        assert result == raw_key

    def test_load_invalid_pem(self, tmp_path):
        """Test loading an invalid PEM returns None."""
        pem_file = tmp_path / "bad_key.pem"
        pem_file.write_text("not a valid pem file")

        result = _load_ed25519_key(str(pem_file))
        assert result is None


class TestGatherIsIntegration:
    """Integration test: GatherIs as an agent tool."""

    def test_gatheris_integrates_with_agent(self):
        """Test that GatherIs can be used as an agent tool."""
        from connectonion import Agent
        from connectonion.core.llm import LLMResponse
        from connectonion.core.usage import TokenUsage

        mock_llm = Mock()
        mock_llm.model = "test-model"
        mock_llm.complete.return_value = LLMResponse(
            content="Test response",
            tool_calls=[],
            raw_response=None,
            usage=TokenUsage(),
        )

        gis = GatherIs()
        agent = Agent("test", llm=mock_llm, tools=[gis], log=False)

        # Verify tools are registered
        assert "browse_feed" in agent.tools
        assert "discover_agents" in agent.tools
        assert "post" in agent.tools
        assert "comment" in agent.tools
