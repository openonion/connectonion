"""
Purpose: Web page fetching and parsing tool for HTTP requests and HTML analysis
LLM-Note:
  Dependencies: imports from [httpx] | imported by [useful_tools/__init__.py] | tested by [tests/unit/test_web_fetch.py]
  Data flow: Agent calls WebFetch methods → httpx.get() fetches URL → returns raw HTML or parsed content (title, links, emails, social links) | analyze_page() and get_contact_info() use LLM for interpretation
  State/Effects: makes HTTP GET requests | no local file persistence | no authentication required | respects timeout setting
  Integration: exposes WebFetch class with fetch(url), strip_tags(html), get_title(html), get_links(html), get_emails(html), get_social_links(html), analyze_page(url), get_contact_info(url) | used as agent tool via Agent(tools=[WebFetch()])
  Performance: network I/O per request | configurable timeout (default 15s) | no caching | high-level methods may call LLM
  Errors: httpx exceptions propagate on network errors | returns error strings for display to user

WebFetch tool for fetching web pages.

Usage:
    from connectonion import Agent, WebFetch

    web = WebFetch()
    agent = Agent("assistant", tools=[web])

    # Agent can now use:
    # Low-level:
    # - fetch(url) - HTTP GET, returns raw HTML
    # - strip_tags(html) - Strip HTML tags, returns body text only
    # - get_title(html) - Get page title
    # - get_links(html) - Extract all links
    # - get_emails(html) - Extract email addresses
    # - get_social_links(html) - Extract social media links
    # High-level (with LLM):
    # - analyze_page(url) - What does this page/company do
    # - get_contact_info(url) - Extract contact information (email, phone, address)
"""

import httpx


class WebFetch:
    """Web fetching tool with single-responsibility functions."""

    def __init__(self, timeout: int = 15):
        """Initialize WebFetch tool.

        Args:
            timeout: Request timeout in seconds (default: 15)
        """
        self.timeout = timeout

    def fetch(self, url: str) -> str:
        """HTTP GET request, returns raw HTML.

        Args:
            url: URL to fetch (e.g., "https://example.com" or "example.com")

        Returns:
            Raw HTML response text
        """
        # Ensure URL has scheme
        if not url.startswith(('http://', 'https://')):
            url = 'https://' + url

        response = httpx.get(
            url,
            follow_redirects=True,
            timeout=self.timeout,
            headers={'User-Agent': 'Mozilla/5.0 (compatible; ResearchBot/1.0)'}
        )
        response.raise_for_status()
        return response.text

    def strip_tags(self, html: str, max_chars: int = 10000) -> str:
        """Strip HTML tags and return plain text from body only.

        Args:
            html: Raw HTML string
            max_chars: Maximum characters to return (default: 10000)

        Returns:
            Clean plain text (body content only)
        """
        from bs4 import BeautifulSoup
        import re

        soup = BeautifulSoup(html, 'html.parser')

        # Only get body content
        body = soup.body if soup.body else soup

        # Remove all non-text elements
        for tag in body(['script', 'style', 'meta', 'link', 'nav', 'footer', 'header', 'aside', 'noscript', 'iframe', 'svg', 'img', 'video', 'audio']):
            tag.decompose()

        # Get text
        text = body.get_text(separator='\n', strip=True)

        # Clean up multiple newlines
        text = re.sub(r'\n{3,}', '\n\n', text)

        return text[:max_chars]

    def get_title(self, html: str) -> str:
        """Get page title from HTML.

        Args:
            html: Raw HTML string

        Returns:
            Page title or empty string if not found
        """
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html, 'html.parser')
        title_tag = soup.find('title')
        return title_tag.get_text(strip=True) if title_tag else ''

    def get_links(self, html: str) -> list:
        """Extract all links from HTML.

        Args:
            html: Raw HTML string

        Returns:
            List of dicts with 'text' and 'href' keys
        """
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html, 'html.parser')
        links = []
        for a in soup.find_all('a', href=True):
            href = a['href']
            text = a.get_text(strip=True)
            if href and not href.startswith('#') and not href.startswith('javascript:'):
                links.append({'text': text, 'href': href})
        return links

    def get_emails(self, html: str) -> list:
        """Extract email addresses from HTML.

        Args:
            html: Raw HTML string

        Returns:
            List of unique email addresses found
        """
        import re

        email_pattern = r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'
        emails = re.findall(email_pattern, html)
        return list(set(emails))

    def get_social_links(self, html: str) -> dict:
        """Extract social media links from HTML.

        Args:
            html: Raw HTML string

        Returns:
            Dict with social platform names as keys and URLs as values
        """
        links = self.get_links(html)
        social_patterns = {
            'twitter': ['twitter.com', 'x.com'],
            'linkedin': ['linkedin.com'],
            'facebook': ['facebook.com'],
            'instagram': ['instagram.com'],
            'youtube': ['youtube.com'],
            'github': ['github.com'],
            'discord': ['discord.gg', 'discord.com'],
        }

        social = {}
        for link in links:
            href = link['href'].lower()
            for platform, patterns in social_patterns.items():
                if any(p in href for p in patterns):
                    social[platform] = link['href']
                    break
        return social

    # === High-level APIs (with LLM) ===

    def analyze_page(self, url: str) -> str:
        """Analyze what a webpage/company does.

        Args:
            url: URL to analyze

        Returns:
            Brief description of what this page/company does
        """
        from connectonion.llm_do import llm_do

        html = self.fetch(url)
        title = self.get_title(html)
        content = self.strip_tags(html, max_chars=6000)

        return llm_do(
            f"Title: {title}\n\nContent:\n{content}",
            system_prompt="Briefly describe what this website/company does in 2-3 sentences. Be concise and factual."
        )

    def get_contact_info(self, url: str) -> str:
        """Extract contact information from a webpage.

        Args:
            url: URL to extract contact info from

        Returns:
            Contact information (email, phone, address, social links)
        """
        from connectonion.llm_do import llm_do

        html = self.fetch(url)
        content = self.strip_tags(html, max_chars=8000)

        return llm_do(
            content,
            system_prompt="Extract any contact information from this page: email addresses, phone numbers, physical addresses, social media links. Return only what you find, or 'No contact info found' if none."
        )
