"""
Purpose: You.com web search, URL content extraction, and cited research for agents that need current information
LLM-Note:
  Dependencies: imports from [os, httpx] | imported by [useful_tools/__init__.py] | tested by [tests/unit/test_youcom_search.py]
  Data flow: youcom_search(query) → reads YDC_API_KEY → POST api.you.com/api/search → returns dict of results (same for contents/research)
  State/Effects: one HTTP request per call | no local state | YDC_API_KEY is read at call time so a key exported later in the session is picked up without re-instantiating anything
  Integration: exposed as agent tools and via `from connectonion import youcom_search, youcom_contents, youcom_research` | opt-in through YDC_API_KEY — with no key every function returns the same auth_required shape and nothing leaves the machine
  Errors: returns {error: auth_required|payment_required|search_failed|contents_failed|research_failed|network_error, message} without echoing the key-bearing header
"""

import os

import httpx

API = "https://api.you.com"
TIMEOUT = 30

NO_KEY = (
    "YDC_API_KEY is not set. Create a key at you.com/platform/api-keys and put "
    "it in ~/.co/keys.env as YDC_API_KEY. Every You.com tool needs it; there "
    "is no unauthenticated path."
)


def _headers() -> dict[str, str]:
    """Build the request headers, reading the key at call time."""
    return {
        "Authorization": f"Bearer {os.getenv('YDC_API_KEY')}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }


def _failure(error: str, message: str, **extra) -> dict[str, object]:
    return {"error": error, "message": message, **extra}


def _post(endpoint: str, payload: dict, error_kind: str) -> dict[str, object]:
    """POST to a You.com endpoint and translate the envelope.

    Raises nothing: every failure path comes back as a dict with an `error`
    key, the same shape the three tools below return.
    """
    try:
        response = httpx.post(
            f"{API}{endpoint}",
            headers=_headers(),
            json=payload,
            timeout=TIMEOUT,
            follow_redirects=True,
        )
    except httpx.RequestError as exc:
        # Exception strings can contain the URL; the class name says the
        # failure without echoing anything the caller could replay.
        return _failure("network_error", f"You.com request failed ({type(exc).__name__}).")

    if response.status_code == 402:
        return _failure(
            "payment_required",
            "You.com returned payment required for this call. An x402-aware "
            "client settles that outside this tool; set YDC_API_KEY to skip it.",
        )
    if response.status_code == 401:
        return _failure(
            "auth_required",
            "You.com rejected the credentials. Check YDC_API_KEY at "
            "you.com/platform/api-keys.",
        )
    if response.is_error:
        return _failure(error_kind, f"You.com returned HTTP {response.status_code}.")

    try:
        body = response.json()
    except ValueError:
        return _failure(error_kind, "You.com returned HTTP 200 without JSON.")

    if not isinstance(body, dict):
        return _failure(error_kind, "You.com returned an invalid response.")
    return body


def youcom_search(query: str, count: int = 10, freshness: str | None = None) -> dict[str, object]:
    """Search the web for current information.

    Args:
        query: What to look for
        count: Number of results (1-20, default: 10)
        freshness: Time filter — 'day', 'week', 'month' or 'year' (optional)

    Returns:
        dict: You.com search results (titles, snippets, URLs), or
        {error, message} — `auth_required` when YDC_API_KEY is not set.
    """
    if not os.getenv("YDC_API_KEY"):
        return _failure("auth_required", NO_KEY)

    payload = {"query": query, "count": min(max(count, 1), 20)}
    if freshness:
        payload["freshness"] = freshness
    return _post("/api/search", payload, "search_failed")


def youcom_contents(urls) -> dict[str, object]:
    """Extract the text content of specific URLs.

    Args:
        urls: One URL, or a list of up to 10

    Returns:
        dict: Extracted content per URL, or {error, message} —
        `auth_required` when YDC_API_KEY is not set.
    """
    if not os.getenv("YDC_API_KEY"):
        return _failure("auth_required", NO_KEY)

    if isinstance(urls, str):
        urls = [urls]
    return _post("/api/contents", {"urls": list(urls)[:10]}, "contents_failed")


def youcom_research(query: str) -> dict[str, object]:
    """Get a one-shot cited synthesis of a research question.

    Args:
        query: The research question or topic

    Returns:
        dict: Synthesized answer with citations, or {error, message} —
        `auth_required` when YDC_API_KEY is not set.
    """
    if not os.getenv("YDC_API_KEY"):
        return _failure("auth_required", NO_KEY)

    return _post("/api/research", {"query": query}, "research_failed")
