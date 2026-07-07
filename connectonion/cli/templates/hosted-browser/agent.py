"""Hosted browser-automation agent.

One shared stealth browser (Patchright, persistent login profile) serves every
chat session; the bind_browser_session plugin routes each session to its own tab.
Site workflows (login, posting, scraping) live in .co/skills/<name>/SKILL.md so
this file stays site-agnostic — see README.md for the skill format.

Run modes:
    python agent.py "check my notifications"   # one-shot local run (develop skills)
    python agent.py                             # serve over HTTP/WS + relay
"""

import sys
import threading
import time
from pathlib import Path

from dotenv import load_dotenv

from connectonion import Agent, host, before_each_tool
from connectonion.useful_plugins import (
    runtime_input,
    image_result_formatter,
    human_jitter,
    no_progress_guard,
    bind_browser_session,
)
from connectonion.useful_plugins.skills import skills as skills_plugin
from connectonion.useful_tools import ask_user
from connectonion.useful_tools.browser_tools import BrowserAutomation

load_dotenv()

# One shared browser: every session shares the login state (cookies persist in
# ~/.co/browser_profile) and drives its own tab in it. Headed, not headless —
# real sites treat headless fingerprints as bots; on a server it renders into
# Xvfb (see Dockerfile). The knobs bound memory on small deploy boxes: an idle
# tab is reclaimed after 10 min and comes back restored to its last URL.
browser = BrowserAutomation(headless=False, tab_idle_ttl=600, max_tabs=3)


class BrowserIdleReaper:
    """Close the shared browser after `ttl` seconds without tool calls, freeing
    Chromium's ~1GB on a small deploy box. The next browser tool relaunches it
    lazily and login survives in the on-disk profile. Register `stamp` as a
    plugin so every tool call resets the idle clock."""

    def __init__(self, browser: BrowserAutomation, ttl: float = 7200, check_every: float = 300):
        self._browser = browser
        self._ttl = ttl
        self._check_every = check_every
        self._last_used = time.monotonic()
        # A lambda, not a bound method: the event wrappers tag handlers by
        # setting an attribute, which bound methods don't accept.
        self.stamp = [before_each_tool(lambda agent: self._touch())]
        threading.Thread(target=self._reap_when_idle, daemon=True).start()

    def _touch(self):
        self._last_used = time.monotonic()

    def _reap_when_idle(self):
        while True:
            time.sleep(self._check_every)
            if self._browser.browser is not None and time.monotonic() - self._last_used > self._ttl:
                try:
                    self._browser.close()
                except Exception:
                    pass  # a failed close must not kill the reaper; retried next check


reaper = BrowserIdleReaper(browser)


# Factory: a fresh Agent per request (own io, own history) so concurrent
# sessions can't read each other's conversation. Only the browser is shared —
# it is safe from any thread, and bind_browser_session gives each session its
# own tab in it.
def create_agent():
    return Agent(
        "browser-agent",
        system_prompt=Path(__file__).parent / "prompts" / "agent.md",
        tools=[browser, ask_user],
        plugins=[
            skills_plugin,            # site workflows from .co/skills/*/SKILL.md
            runtime_input,
            image_result_formatter,   # keep only the last 3 screenshots in LLM context
            human_jitter,             # organic pointer motion before clicks
            no_progress_guard(),      # halt a loop stuck repeating the same call
            bind_browser_session,     # each session gets its own tab in the shared browser
            reaper.stamp,             # any tool call resets the browser idle clock
        ],
        model="co/gemini-3-flash-preview",
        max_iterations=200,           # a normal site flow is ~15-20 steps; backstop
    )


def create_hosted_agent():
    agent = create_agent()
    # This helper blocks on stdin, which never answers behind host(). Hosted
    # login handoffs (credentials, 2FA) go through ask_user instead.
    agent.tools.remove("wait_for_manual_login")
    return agent


if __name__ == "__main__":
    if len(sys.argv) > 1:
        # Local one-shot run keeps wait_for_manual_login: with a headed browser
        # and a real terminal you can log in by hand once, and the profile keeps it.
        print(create_agent().input(" ".join(sys.argv[1:])))
    else:
        host(create_hosted_agent)
