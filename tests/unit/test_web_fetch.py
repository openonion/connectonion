"""Unit tests for connectonion/useful_tools/web_fetch.py

Tests cover:
- fetch: HTTP GET with URL normalization
- strip_tags: HTML to plain text conversion
- get_title: Page title extraction
- get_links: Link extraction
- get_emails: Email address extraction
- get_social_links: Social media link detection
- analyze_page: High-level page analysis (mocked LLM)
- get_contact_info: Contact info extraction (mocked LLM)
"""

import pytest
from unittest.mock import Mock, patch, MagicMock

from connectonion.useful_tools.web_fetch import WebFetch


SAMPLE_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>Test Page Title</title>
    <script>console.log('test');</script>
    <style>.test { color: red; }</style>
</head>
<body>
    <header>Header content</header>
    <nav>Navigation</nav>
    <main>
        <h1>Welcome to Example.com</h1>
        <p>This is a test paragraph with <a href="https://example.com/about">About link</a>.</p>
        <p>Contact us at test@example.com or info@test.org</p>
        <a href="https://twitter.com/example">Twitter</a>
        <a href="https://github.com/example">GitHub</a>
        <a href="#anchor">Anchor link</a>
        <a href="javascript:void(0)">JS link</a>
    </main>
    <footer>Footer content</footer>
</body>
</html>
"""


class TestWebFetchInit:
    """Tests for WebFetch initialization."""

    def test_default_timeout(self):
        """Test default timeout is 15 seconds."""
        web = WebFetch()
        assert web.timeout == 15

    def test_custom_timeout(self):
        """Test custom timeout is set."""
        web = WebFetch(timeout=30)
        assert web.timeout == 30


class TestFetch:
    """Tests for fetch method."""

    @patch('connectonion.useful_tools.web_fetch.httpx.get')
    def test_fetch_with_scheme(self, mock_get):
        """Test fetch with full URL including scheme."""
        mock_response = Mock()
        mock_response.text = "<html>content</html>"
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        web = WebFetch()
        result = web.fetch("https://example.com")

        assert result == "<html>content</html>"
        mock_get.assert_called_once()
        call_args = mock_get.call_args
        assert call_args[0][0] == "https://example.com"

    @patch('connectonion.useful_tools.web_fetch.httpx.get')
    def test_fetch_adds_https_scheme(self, mock_get):
        """Test fetch adds https:// to URL without scheme."""
        mock_response = Mock()
        mock_response.text = "<html>content</html>"
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        web = WebFetch()
        web.fetch("example.com")

        call_args = mock_get.call_args
        assert call_args[0][0] == "https://example.com"

    @patch('connectonion.useful_tools.web_fetch.httpx.get')
    def test_fetch_follows_redirects(self, mock_get):
        """Test fetch follows redirects."""
        mock_response = Mock()
        mock_response.text = "<html>content</html>"
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        web = WebFetch()
        web.fetch("https://example.com")

        call_kwargs = mock_get.call_args[1]
        assert call_kwargs['follow_redirects'] is True

    @patch('connectonion.useful_tools.web_fetch.httpx.get')
    def test_fetch_uses_timeout(self, mock_get):
        """Test fetch uses configured timeout."""
        mock_response = Mock()
        mock_response.text = "<html>content</html>"
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        web = WebFetch(timeout=30)
        web.fetch("https://example.com")

        call_kwargs = mock_get.call_args[1]
        assert call_kwargs['timeout'] == 30

    @patch('connectonion.useful_tools.web_fetch.httpx.get')
    def test_fetch_has_user_agent(self, mock_get):
        """Test fetch includes User-Agent header."""
        mock_response = Mock()
        mock_response.text = "<html>content</html>"
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        web = WebFetch()
        web.fetch("https://example.com")

        call_kwargs = mock_get.call_args[1]
        assert 'User-Agent' in call_kwargs['headers']


class TestStripTags:
    """Tests for strip_tags method."""

    def test_strip_tags_basic(self):
        """Test basic HTML tag stripping."""
        web = WebFetch()
        result = web.strip_tags(SAMPLE_HTML)

        assert "Welcome to Example.com" in result
        assert "test paragraph" in result
        assert "<html>" not in result
        assert "<script>" not in result

    def test_strip_tags_removes_scripts(self):
        """Test that script tags are removed."""
        web = WebFetch()
        result = web.strip_tags(SAMPLE_HTML)

        assert "console.log" not in result

    def test_strip_tags_removes_styles(self):
        """Test that style tags are removed."""
        web = WebFetch()
        result = web.strip_tags(SAMPLE_HTML)

        assert ".test" not in result
        assert "color: red" not in result

    def test_strip_tags_max_chars(self):
        """Test max_chars truncation."""
        web = WebFetch()
        result = web.strip_tags(SAMPLE_HTML, max_chars=50)

        assert len(result) <= 50

    def test_strip_tags_empty_html(self):
        """Test strip_tags with empty HTML."""
        web = WebFetch()
        result = web.strip_tags("")

        assert result == ""

    def test_strip_tags_no_body(self):
        """Test strip_tags when no body tag exists."""
        web = WebFetch()
        result = web.strip_tags("<html><p>No body tag</p></html>")

        assert "No body tag" in result


class TestGetTitle:
    """Tests for get_title method."""

    def test_get_title_basic(self):
        """Test basic title extraction."""
        web = WebFetch()
        result = web.get_title(SAMPLE_HTML)

        assert result == "Test Page Title"

    def test_get_title_no_title(self):
        """Test get_title when no title tag exists."""
        web = WebFetch()
        result = web.get_title("<html><body>No title</body></html>")

        assert result == ""

    def test_get_title_with_whitespace(self):
        """Test get_title strips whitespace."""
        web = WebFetch()
        result = web.get_title("<html><head><title>  Spaced Title  </title></head></html>")

        assert result == "Spaced Title"


class TestGetLinks:
    """Tests for get_links method."""

    def test_get_links_extracts_links(self):
        """Test basic link extraction."""
        web = WebFetch()
        result = web.get_links(SAMPLE_HTML)

        hrefs = [link['href'] for link in result]
        assert "https://example.com/about" in hrefs
        assert "https://twitter.com/example" in hrefs
        assert "https://github.com/example" in hrefs

    def test_get_links_skips_anchors(self):
        """Test that anchor links (#) are skipped."""
        web = WebFetch()
        result = web.get_links(SAMPLE_HTML)

        hrefs = [link['href'] for link in result]
        assert "#anchor" not in hrefs

    def test_get_links_skips_javascript(self):
        """Test that javascript: links are skipped."""
        web = WebFetch()
        result = web.get_links(SAMPLE_HTML)

        hrefs = [link['href'] for link in result]
        assert not any(h.startswith('javascript:') for h in hrefs)

    def test_get_links_includes_text(self):
        """Test that link text is included."""
        web = WebFetch()
        result = web.get_links(SAMPLE_HTML)

        texts = [link['text'] for link in result]
        assert "About link" in texts
        assert "Twitter" in texts

    def test_get_links_empty_html(self):
        """Test get_links with no links."""
        web = WebFetch()
        result = web.get_links("<html><body>No links here</body></html>")

        assert result == []


class TestGetEmails:
    """Tests for get_emails method."""

    def test_get_emails_extracts_emails(self):
        """Test basic email extraction."""
        web = WebFetch()
        result = web.get_emails(SAMPLE_HTML)

        assert "test@example.com" in result
        assert "info@test.org" in result

    def test_get_emails_unique(self):
        """Test that emails are deduplicated."""
        web = WebFetch()
        html = "test@example.com test@example.com test@example.com"
        result = web.get_emails(html)

        assert len(result) == 1
        assert result[0] == "test@example.com"

    def test_get_emails_various_formats(self):
        """Test various email formats."""
        web = WebFetch()
        html = """
        user.name@domain.co.uk
        user+tag@example.com
        user123@test.org
        """
        result = web.get_emails(html)

        assert "user.name@domain.co.uk" in result
        assert "user+tag@example.com" in result
        assert "user123@test.org" in result

    def test_get_emails_empty(self):
        """Test get_emails with no emails."""
        web = WebFetch()
        result = web.get_emails("<html><body>No emails</body></html>")

        assert result == []


class TestGetSocialLinks:
    """Tests for get_social_links method."""

    def test_get_social_links_twitter(self):
        """Test Twitter link detection."""
        web = WebFetch()
        result = web.get_social_links(SAMPLE_HTML)

        assert 'twitter' in result
        assert "twitter.com/example" in result['twitter']

    def test_get_social_links_github(self):
        """Test GitHub link detection."""
        web = WebFetch()
        result = web.get_social_links(SAMPLE_HTML)

        assert 'github' in result
        assert "github.com/example" in result['github']

    def test_get_social_links_x_dot_com(self):
        """Test x.com (Twitter) detection."""
        web = WebFetch()
        html = '<a href="https://x.com/example">X</a>'
        result = web.get_social_links(html)

        assert 'twitter' in result
        assert "x.com/example" in result['twitter']

    def test_get_social_links_all_platforms(self):
        """Test all supported platforms."""
        web = WebFetch()
        html = """
        <a href="https://twitter.com/test">Twitter</a>
        <a href="https://linkedin.com/in/test">LinkedIn</a>
        <a href="https://facebook.com/test">Facebook</a>
        <a href="https://instagram.com/test">Instagram</a>
        <a href="https://youtube.com/test">YouTube</a>
        <a href="https://github.com/test">GitHub</a>
        <a href="https://discord.gg/test">Discord</a>
        """
        result = web.get_social_links(html)

        assert 'twitter' in result
        assert 'linkedin' in result
        assert 'facebook' in result
        assert 'instagram' in result
        assert 'youtube' in result
        assert 'github' in result
        assert 'discord' in result

    def test_get_social_links_empty(self):
        """Test get_social_links with no social links."""
        web = WebFetch()
        result = web.get_social_links("<html><body>No social links</body></html>")

        assert result == {}


class TestAnalyzePage:
    """Tests for analyze_page method (mocked LLM)."""

    def test_analyze_page_calls_llm(self):
        """Test that analyze_page calls llm_do with page content."""
        import importlib
        llm_do_module = importlib.import_module('connectonion.llm_do')

        with patch.object(llm_do_module, 'llm_do') as mock_llm_do:
            with patch('connectonion.useful_tools.web_fetch.httpx.get') as mock_get:
                mock_response = Mock()
                mock_response.text = SAMPLE_HTML
                mock_response.raise_for_status = Mock()
                mock_get.return_value = mock_response
                mock_llm_do.return_value = "This is a test website."

                web = WebFetch()
                result = web.analyze_page("https://example.com")

                assert result == "This is a test website."
                mock_llm_do.assert_called_once()
                call_args = mock_llm_do.call_args
                assert "Test Page Title" in call_args[0][0]

    def test_analyze_page_uses_system_prompt(self):
        """Test that analyze_page uses appropriate system prompt."""
        import importlib
        llm_do_module = importlib.import_module('connectonion.llm_do')

        with patch.object(llm_do_module, 'llm_do') as mock_llm_do:
            with patch('connectonion.useful_tools.web_fetch.httpx.get') as mock_get:
                mock_response = Mock()
                mock_response.text = SAMPLE_HTML
                mock_response.raise_for_status = Mock()
                mock_get.return_value = mock_response
                mock_llm_do.return_value = "Analysis result"

                web = WebFetch()
                web.analyze_page("https://example.com")

                call_kwargs = mock_llm_do.call_args[1]
                assert "describe" in call_kwargs['system_prompt'].lower()


class TestGetContactInfo:
    """Tests for get_contact_info method (mocked LLM)."""

    def test_get_contact_info_calls_llm(self):
        """Test that get_contact_info calls llm_do."""
        import importlib
        llm_do_module = importlib.import_module('connectonion.llm_do')

        with patch.object(llm_do_module, 'llm_do') as mock_llm_do:
            with patch('connectonion.useful_tools.web_fetch.httpx.get') as mock_get:
                mock_response = Mock()
                mock_response.text = SAMPLE_HTML
                mock_response.raise_for_status = Mock()
                mock_get.return_value = mock_response
                mock_llm_do.return_value = "Email: test@example.com"

                web = WebFetch()
                result = web.get_contact_info("https://example.com")

                assert result == "Email: test@example.com"
                mock_llm_do.assert_called_once()

    def test_get_contact_info_uses_system_prompt(self):
        """Test that get_contact_info uses appropriate system prompt."""
        import importlib
        llm_do_module = importlib.import_module('connectonion.llm_do')

        with patch.object(llm_do_module, 'llm_do') as mock_llm_do:
            with patch('connectonion.useful_tools.web_fetch.httpx.get') as mock_get:
                mock_response = Mock()
                mock_response.text = SAMPLE_HTML
                mock_response.raise_for_status = Mock()
                mock_get.return_value = mock_response
                mock_llm_do.return_value = "Contact info"

                web = WebFetch()
                web.get_contact_info("https://example.com")

                call_kwargs = mock_llm_do.call_args[1]
                assert "contact" in call_kwargs['system_prompt'].lower()


class TestWebFetchIntegration:
    """Integration tests for WebFetch as agent tool."""

    def test_webfetch_integrates_with_agent(self):
        """Test that WebFetch can be used as an agent tool."""
        from connectonion import Agent
        from connectonion.core.llm import LLMResponse
        from connectonion.core.usage import TokenUsage

        # Create mock LLM
        mock_llm = Mock()
        mock_llm.model = "test-model"
        mock_llm.complete.return_value = LLMResponse(
            content="Test response",
            tool_calls=[],
            raw_response=None,
            usage=TokenUsage(),
        )

        web = WebFetch()

        # Should not raise
        agent = Agent(
            "test",
            llm=mock_llm,
            tools=[web],
            log=False,
        )

        # Verify tools are registered
        assert 'fetch' in agent.tools
        assert 'strip_tags' in agent.tools
        assert 'get_title' in agent.tools
        assert 'get_links' in agent.tools
        assert 'get_emails' in agent.tools
        assert 'get_social_links' in agent.tools
        assert 'analyze_page' in agent.tools
        assert 'get_contact_info' in agent.tools
