"""
Purpose: You.com search and content tools for current web information, URL content extraction, and cited research
LLM-Note:
  Dependencies: imports from [httpx, json] | imported by [useful_tools/__init__.py] | tested by [tests/unit/test_youcom_search.py]
  Data flow: Agent calls YoucomSearch methods → httpx requests to You.com API → returns search results, URL contents, or research synthesis
  State/Effects: makes HTTP requests to api.you.com | requires YDC_API_KEY env var for authenticated access | no local file persistence
  Integration: exposes YoucomSearch class with search(query), get_contents(urls), research(query) | used as agent tool via Agent(tools=[YoucomSearch()])
  Performance: network I/O per request | configurable timeout (default 30s) | API rate limits apply | authenticated requests preferred
  Errors: httpx exceptions propagate on network errors | graceful fallback to free search when no API key

You.com search and content extraction tools for AI agents.

Usage:
    from connectonion import Agent, YoucomSearch
    
    search = YoucomSearch()
    agent = Agent("assistant", tools=[search])
    
    # Agent can now use:
    # - search(query) - Current web search with snippets and links
    # - get_contents(urls) - Extract content from specific URLs 
    # - research(query) - One-shot cited research synthesis (requires API key)

Environment Variables:
    YDC_API_KEY: Optional You.com API key for authenticated access
                 If not provided, falls back to free search with basic functionality
    
    YOUCOM_BASE_URL: Optional API base URL override (default: https://api.you.com)
"""

import httpx
import json
import os
from typing import List, Dict, Optional, Union


class YoucomSearch:
    """You.com search and content tools with optional authentication."""

    def __init__(self, timeout: int = 30, base_url: Optional[str] = None):
        """Initialize You.com search tool.

        Args:
            timeout: Request timeout in seconds (default: 30)
            base_url: API base URL override (default: https://api.you.com)
        """
        self.timeout = timeout
        self.base_url = base_url or os.getenv('YOUCOM_BASE_URL', 'https://api.you.com')
        self.api_key = os.getenv('YDC_API_KEY')
        
        # Setup headers
        self.headers = {
            'User-Agent': 'ConnectOnion/1.0 (Agent Framework)',
            'Accept': 'application/json',
            'Content-Type': 'application/json'
        }
        
        if self.api_key:
            self.headers['Authorization'] = f'Bearer {self.api_key}'

    def search(self, query: str, count: int = 10, safesearch: str = 'moderate', 
               freshness: Optional[str] = None, livecrawl: Optional[str] = None) -> str:
        """Search the web using You.com API.

        Args:
            query: Search query string
            count: Number of results to return (1-20, default: 10)
            safesearch: Safe search filter ('strict', 'moderate', 'off', default: 'moderate')
            freshness: Time filter ('day', 'week', 'month', 'year', optional)
            livecrawl: Live crawl mode ('web' for full content, optional)

        Returns:
            JSON string with search results containing snippets, titles, URLs, and metadata
        """
        params = {
            'query': query,
            'count': min(max(count, 1), 20),
            'safesearch': safesearch
        }
        
        if freshness:
            params['freshness'] = freshness
        if livecrawl:
            params['livecrawl'] = livecrawl

        try:
            response = httpx.post(
                f'{self.base_url}/api/search',
                headers=self.headers,
                json=params,
                timeout=self.timeout,
                follow_redirects=True
            )
            
            # Handle payment required (402) for x402-aware clients
            if response.status_code == 402:
                return json.dumps({
                    'error': 'payment_required',
                    'message': 'This query requires payment. If you have an x402-aware MCP client, it will handle payment automatically.',
                    'fallback': 'Consider using free search with basic functionality.'
                })
            
            response.raise_for_status()
            return response.text
            
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401:
                # Fallback to free search if authentication fails
                return self._free_search(query, count, safesearch)
            else:
                return json.dumps({
                    'error': 'search_failed',
                    'status_code': e.response.status_code,
                    'message': f'Search request failed: {e.response.text}'
                })
        except Exception as e:
            return json.dumps({
                'error': 'network_error', 
                'message': f'Failed to connect to You.com API: {str(e)}'
            })

    def get_contents(self, urls: Union[str, List[str]], 
                     include_raw_html: bool = False) -> str:
        """Extract content from specific URLs using You.com API.

        Args:
            urls: Single URL string or list of URLs to fetch content from
            include_raw_html: Whether to include raw HTML in response (default: False)

        Returns:
            JSON string with extracted content, titles, and metadata for each URL
        """
        if isinstance(urls, str):
            urls = [urls]
            
        params = {
            'urls': urls[:10],  # Limit to 10 URLs for performance
            'include_raw_html': include_raw_html
        }

        try:
            response = httpx.post(
                f'{self.base_url}/api/contents',
                headers=self.headers,
                json=params,
                timeout=self.timeout,
                follow_redirects=True
            )
            
            # Handle payment required (402)
            if response.status_code == 402:
                return json.dumps({
                    'error': 'payment_required',
                    'message': 'URL content extraction requires payment or authentication.',
                    'fallback': 'Consider providing a You.com API key via YDC_API_KEY environment variable.'
                })
            
            response.raise_for_status()
            return response.text
            
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401:
                return json.dumps({
                    'error': 'auth_required',
                    'message': 'URL content extraction requires authentication. Set YDC_API_KEY environment variable.',
                    'urls_requested': urls
                })
            else:
                return json.dumps({
                    'error': 'contents_failed',
                    'status_code': e.response.status_code,
                    'message': f'Content extraction failed: {e.response.text}',
                    'urls_requested': urls
                })
        except Exception as e:
            return json.dumps({
                'error': 'network_error',
                'message': f'Failed to connect to You.com API: {str(e)}',
                'urls_requested': urls
            })

    def research(self, query: str, count: int = 10) -> str:
        """Get cited research synthesis using You.com API (requires authentication).

        Args:
            query: Research question or topic
            count: Number of sources to synthesize (1-20, default: 10)

        Returns:
            JSON string with synthesized research and citations
        """
        if not self.api_key:
            return json.dumps({
                'error': 'auth_required',
                'message': 'Research synthesis requires authentication. Set YDC_API_KEY environment variable.',
                'fallback': 'Use search() method for basic web search without synthesis.'
            })

        params = {
            'query': query,
            'count': min(max(count, 1), 20)
        }

        try:
            response = httpx.post(
                f'{self.base_url}/api/research',
                headers=self.headers,
                json=params,
                timeout=self.timeout,
                follow_redirects=True
            )
            
            # Handle payment required (402)
            if response.status_code == 402:
                return json.dumps({
                    'error': 'payment_required',
                    'message': 'Research synthesis requires payment.',
                    'fallback': 'Use basic search() method for individual results.'
                })
            
            response.raise_for_status()
            return response.text
            
        except httpx.HTTPStatusError as e:
            return json.dumps({
                'error': 'research_failed',
                'status_code': e.response.status_code,
                'message': f'Research request failed: {e.response.text}'
            })
        except Exception as e:
            return json.dumps({
                'error': 'network_error',
                'message': f'Failed to connect to You.com API: {str(e)}'
            })

    def _free_search(self, query: str, count: int = 10, 
                     safesearch: str = 'moderate') -> str:
        """Fallback to free search when authentication fails.
        
        Args:
            query: Search query string
            count: Number of results (limited in free tier)
            safesearch: Safe search filter
            
        Returns:
            JSON string with basic search results
        """
        params = {
            'query': query,
            'count': min(count, 5),  # Free tier typically has lower limits
            'safesearch': safesearch
        }

        try:
            # Use free profile endpoint
            response = httpx.post(
                f'{self.base_url}/api/search?profile=free',
                headers={'User-Agent': self.headers['User-Agent']},
                json=params,
                timeout=self.timeout,
                follow_redirects=True
            )
            
            response.raise_for_status()
            
            # Add fallback notice to results
            result_data = json.loads(response.text)
            if isinstance(result_data, dict):
                result_data['_fallback_notice'] = 'Using free search - limited functionality. Set YDC_API_KEY for full features.'
            
            return json.dumps(result_data)
            
        except Exception as e:
            return json.dumps({
                'error': 'free_search_failed',
                'message': f'Both authenticated and free search failed: {str(e)}',
                'suggestion': 'Check your network connection and try again.'
            })