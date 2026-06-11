"""
Purpose: Auto-generated ConnectOnion tools from browser-use's full action registry
LLM-Note:
  Dependencies: imports from [browser_use] | imported by [useful_tools/__init__.py]
  Data flow: _register_actions() reads Tools().registry → generates sync method per action → agent calls methods → _act() → registry.execute_action() → BrowserSession
  State/Effects: persistent BrowserSession with all watchdogs | methods auto-generated at init | watchdog events queued for agent via get_events()
  Integration: exposes BrowserTools class — every browser-use action becomes a ConnectOnion tool automatically | new browser-use actions appear without code changes

Browser automation — all browser-use actions as ConnectOnion tools, auto-generated from
the registry. When browser-use adds new actions, they appear automatically.

Usage:
    from connectonion.useful_tools.browser import BrowserTools

    browser = BrowserTools()
    agent = Agent("researcher", tools=[browser])

    # All browser-use actions available:
    # browser.navigate("https://example.com")
    # browser.get_content()        → page text + [index] numbers
    # browser.click(21)            → click element [21]
    # browser.input(3, "query")    → type into element [3]
    # browser.search("python")     → web search
    # browser.scroll()             → scroll down
    # browser.evaluate("document.title")  → run JS
    # browser.screenshot()         → take screenshot
    # browser.get_events()         → check watchdog notifications
    # ... every other browser-use action, automatically

    browser.close()

Requires:
    pip install browser-use
    playwright install chromium
"""

import asyncio
import threading

# Actions that require special LLM params or are ConnectOnion-level concerns — skip auto-gen
_SKIP_ACTIONS = {"done", "extract", "upload_file", "write_file", "replace_file", "read_file", "close"}


class BrowserUseTools:
    """All browser-use actions as ConnectOnion tools. Auto-generated from the registry."""

    def __init__(self, headless: bool = True):
        """Initialize browser session and auto-generate tool methods.

        Args:
            headless: Run without visible window (default: True). Set False to watch.
        """
        self.headless = headless
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._loop.run_forever, daemon=True)
        self._thread.start()
        self._session = None
        self._tools = None
        self._event_queue = []
        self._run(self._start())
        self._register_actions()

    def _run(self, coro):
        return asyncio.run_coroutine_threadsafe(coro, self._loop).result()

    async def _start(self):
        from browser_use.browser.session import BrowserSession
        from browser_use.browser.profile import BrowserProfile
        from browser_use.tools.service import Tools
        from browser_use.browser.events import FileDownloadedEvent, BrowserErrorEvent

        profile = BrowserProfile(headless=self.headless)
        self._session = BrowserSession(browser_profile=profile)
        self._tools = Tools()
        await self._session.start()

        # Bridge watchdog events → agent-readable queue
        self._session.event_bus.on(FileDownloadedEvent, self._on_download)
        self._session.event_bus.on(BrowserErrorEvent, self._on_browser_error)

    async def _on_download(self, event):
        self._event_queue.append(
            f"Download complete: {event.file_name} → {event.path} ({event.file_type or 'unknown type'})"
        )

    async def _on_browser_error(self, event):
        self._event_queue.append(f"Browser error [{event.error_type}]: {event.message}")

    def _act(self, action_name: str, params: dict) -> str:
        async def _exec():
            result = await self._tools.registry.execute_action(
                action_name=action_name,
                params=params,
                browser_session=self._session,
            )
            if result.error:
                return f"Error: {result.error}"
            return result.extracted_content or result.long_term_memory or "Done"

        return self._run(_exec())

    def _register_actions(self):
        """Read browser-use's registry and create a tool method for every action."""
        from pydantic_core import PydanticUndefined

        for action_name, action in self._tools.registry.registry.actions.items():
            if action_name in _SKIP_ACTIONS:
                continue
            method = self._make_method(action_name, action)
            setattr(self, action_name, method)

    def _make_method(self, action_name, action):
        """Generate a properly-typed sync method from a browser-use action."""
        from pydantic_core import PydanticUndefined

        fields = action.param_model.model_fields

        # NoParamsAction has only a dummy 'description' field — treat as zero-arg
        is_no_params = list(fields.keys()) == ["description"]
        if is_no_params:
            fields = {}

        defaults = {}
        param_parts = []
        kwargs_parts = []

        for name, info in fields.items():
            has_default = info.default is not PydanticUndefined
            if has_default:
                defaults[name] = info.default
                param_parts.append(f"{name}=_defaults['{name}']")
            else:
                param_parts.append(name)
            kwargs_parts.append(f'"{name}": {name}')

        param_str = ", ".join(param_parts)
        kwargs_str = ", ".join(kwargs_parts)

        if fields:
            code = (
                f"def {action_name}({param_str}) -> str:\n"
                f"    return _self._act('{action_name}', {{{kwargs_str}}})"
            )
        else:
            code = f"def {action_name}() -> str:\n    return _self._act('{action_name}', {{}})"

        ns = {"_self": self, "_defaults": defaults}
        exec(code, ns)
        fn = ns[action_name]

        # Set type annotations so ConnectOnion's tool_factory builds the correct schema
        fn.__annotations__ = {k: v.annotation for k, v in fields.items()} | {"return": str}

        # Build docstring from action description + field descriptions
        doc_lines = [action.description or f"Browser action: {action_name}."]
        arg_docs = [(k, v.description) for k, v in fields.items() if v.description]
        if arg_docs:
            doc_lines.append("\nArgs:")
            for field_name, field_desc in arg_docs:
                doc_lines.append(f"    {field_name}: {field_desc}")
        doc_lines.append("\nReturns:\n    Result or confirmation message")
        fn.__doc__ = "\n".join(doc_lines)

        return fn

    # ── Special methods not in the registry ─────────────────────────────────

    def get_content(self) -> str:
        """Get current page content with interactive element indices.
        Indices like [21] can be passed to click() and input().
        Always call get_content() after navigation to get fresh indices.

        Returns:
            Page text with numbered interactive elements
        """
        return self._run(self._session.get_state_as_text())

    def get_events(self) -> str:
        """Check for watchdog notifications (completed downloads, browser errors).
        Call this periodically if you expect downloads or errors.

        Returns:
            Recent browser events, or 'No events' if none
        """
        if not self._event_queue:
            return "No events"
        events = list(self._event_queue)
        self._event_queue.clear()
        return "\n".join(events)

    def current_url(self) -> str:
        """Get the current page URL.

        Returns:
            Current URL string
        """
        async def _url():
            return await self._session.get_current_page_url()

        return self._run(_url())

    def close(self) -> str:
        """Close the browser and release all resources.

        Returns:
            Confirmation message
        """
        self._run(self._session.kill())
        self._loop.call_soon_threadsafe(self._loop.stop)
        return "Browser closed"
