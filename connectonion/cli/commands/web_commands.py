"""
Purpose: `co search` and `co fetch` — the co ai web tools, callable from any shell or skill
LLM-Note:
  Dependencies: imports from [useful_tools/search_engines, useful_tools/page_fetch, command_tips] | imported by [cli/main.py] | tested by [tests/unit/test_web_commands.py]
  Data flow: argv → search()/fetch_page() → text or --json on stdout; failures and the next step on stderr
  Integration: handle_search(query, engine, count, as_json) -> exit code; handle_fetch(url, prompt, max_chars, as_json) -> exit code

The same functions the agent calls, so a skill written for Claude Code that
shells out to "search the web" has a command to shell out to, and a human can
see exactly what the agent saw.
"""

import json
import shlex
import sys

from .command_tips import mark_next_step_named, selected_tip, tips_enabled


def _next(step: str) -> None:
    # stderr, so `--json` stdout stays parseable.
    if step and tips_enabled():
        print(f"Next: {selected_tip(step)}", file=sys.stderr)
        mark_next_step_named()


def _fail(message: str, next_step: str) -> int:
    print(message, file=sys.stderr)
    _next(next_step)
    return 1


def handle_search(query: str, engine: str, count: int, as_json: bool) -> int:
    from ...useful_tools.search_engines import SearchError, format_results, search

    try:
        found = search(query, engine, count)
    except SearchError as error:
        if error.code == "bad_engine":
            next_step = f"co search {shlex.quote(query)}"
        elif engine == "ddg":
            next_step = "co search --help"
        else:   # out of credits, no key, or the engine is down: the free one still works
            next_step = f"co search {shlex.quote(query)} --engine ddg"
        return _fail(f"Search failed ({error.code}): {error} {error.hint}".strip(), next_step)
    if as_json:
        print(json.dumps(found, ensure_ascii=False, indent=2))
    else:
        print(format_results(found))
    if found["results"]:
        _next(f"co fetch {shlex.quote(found['results'][0]['url'])}")
    return 0


def handle_fetch(url: str, prompt: str, max_chars: int, as_json: bool) -> int:
    import httpx

    from ...useful_tools.page_fetch import FetchError, _render, fetch_page, web_fetch

    try:
        page = fetch_page(url)
    except FetchError as error:
        return _fail(f"Fetch failed: {error} {error.hint}".strip(), f"curl -sL {shlex.quote(url)}" if "curl" in error.hint else "")
    except httpx.RequestError as error:
        return _fail(f"Fetch failed: could not connect to {url} ({type(error).__name__}).", "")
    if as_json:
        print(json.dumps(page, ensure_ascii=False, indent=2))
    elif prompt:
        print(web_fetch(url, prompt=prompt))   # the page is cached; this spends only the answer
    else:
        print(_render(page, max_chars))
    if page["redirect"]:
        _next(f"co fetch {shlex.quote(page['redirect'])}")
    return 0
