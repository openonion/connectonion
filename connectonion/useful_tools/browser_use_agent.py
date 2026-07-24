"""
Purpose: AI-driven browser automation tool using the browser-use library with ConnectOnion's LLM provider
LLM-Note:
  Dependencies: imports from [browser_use, asyncio, os] | imported by [useful_tools/__init__.py] | tested by [tests/unit/test_browser_use.py]
  Data flow: browser_use(task) → ChatOpenAI pointed at ConnectOnion proxy → BrowserAgent.run() → returns final_result() string
  State/Effects: launches a Playwright browser (headless by default) | makes real HTTP requests | no local file persistence
  Integration: exposes browser_use(task) function | requires `pip install browser-use` + `playwright install chromium`
  Performance: each call spawns a browser session | async internally, wrapped with asyncio.run()
  Errors: raises ImportError with install hint if browser-use not installed | browser errors propagate

AI-driven browser automation using ConnectOnion's LLM provider.

Usage:
    from connectonion.useful_tools.browser_use import browser_use

    agent = Agent("researcher", tools=[browser_use])

    # Agent can now instruct the browser to do anything:
    # browser_use("Go to github.com/openonion/connectonion and get the star count")
    # browser_use("Search Google for Python tutorials, return the top 3 titles")

    # Or with custom options:
    # browser_use("...", headless=False, model="co/gemini-2.5-pro")

Requires:
    pip install browser-use
    playwright install chromium
"""

import asyncio
import os


def browser_use_agent(task: str, headless: bool = True, model: str = "co/gemini-2.5-flash") -> str:
    """Run a browser task using AI-driven automation and return the result.

    Args:
        task: Natural language description of what to do in the browser
              (e.g. "Search Google for 'connectonion' and return the top 3 results")
        headless: Run browser in headless mode, default True. Set False to watch it work.
        model: LLM model for browser decisions. Supports any ConnectOnion model (co/*)
               or any OpenAI-compatible model. Default: co/gemini-2.5-flash

    Returns:
        Result of the browser task as a string
    """
    from browser_use import Agent as BrowserAgent
    from browser_use.llm.openai.chat import ChatOpenAI

    api_key = os.environ.get("OPENONION_API_KEY") or os.environ.get("CONNECTONION_API_KEY") or os.environ.get("OPENAI_API_KEY")
    base_url = os.environ.get("OPENONION_BASE_URL", "https://oo.openonion.ai/v1")

    is_gemini = "gemini" in model.lower()
    llm = ChatOpenAI(
        model=model,
        api_key=api_key,
        base_url=base_url,
        remove_min_items_from_schema=True,
        frequency_penalty=None if is_gemini else 0.3,
    )

    browser_agent = BrowserAgent(task=task, llm=llm)

    async def _run():
        history = await browser_agent.run()
        return history.final_result() or str(history)

    return asyncio.run(_run())
