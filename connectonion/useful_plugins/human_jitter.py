"""
LLM-Note: Mouse-movement plugin.

Purpose: Move the cursor along an organic path before a click instead of teleporting
straight to the target. Some interfaces only reveal or enable a control after real
pointer movement (hover menus, lazy-loaded widgets, drag affordances), so a single
teleport-click can land on nothing; a short wander first makes the interaction land.
Use it on sites whose terms permit automation.

Data flow: before_each_tool event -> read agent.current_session['pending_tool'] ->
if its name starts with 'click', grab the BrowserAutomation instance off the tool
registry (agent.tools.browserautomation) and dispatch jitter() onto the browser's
single worker thread (Playwright is not thread-safe).

Why before_each_tool (not after_tools): this is the only hook that fires
synchronously between "LLM picked a click tool" and "Playwright performs the click",
which is exactly where pre-click motion belongs.

Why a plugin (not baked into BrowserAutomation.click): jitter is non-deterministic
and opt-in. Forcing it on every browser user would make clicks non-reproducible for
tests and agents that don't want it. Agents opt in with plugins=[human_jitter].

State/Effects: moves the mouse cursor via Playwright; no agent state. Best-effort —
if the page is mid-navigation when jitter reads the viewport, the click must still
proceed, so that transient failure is caught and logged, never raised.
"""

import random
import time
from typing import TYPE_CHECKING

from ..core.events import before_each_tool

if TYPE_CHECKING:
    from ..core.agent import Agent


def jitter(page):
    """Wander the mouse through a few random points on the page.

    Must run on the browser's worker thread (Playwright is single-threaded).
    """
    w, h = page.evaluate("() => [window.innerWidth, window.innerHeight]")
    x = random.uniform(w * 0.2, w * 0.8)
    y = random.uniform(h * 0.2, h * 0.8)
    page.mouse.move(x, y, steps=random.randint(8, 16))
    for _ in range(random.randint(2, 4)):
        x = min(max(x + random.uniform(-120, 120), 1), w - 1)
        y = min(max(y + random.uniform(-90, 90), 1), h - 1)
        page.mouse.move(x, y, steps=random.randint(6, 14))
        time.sleep(random.uniform(0.03, 0.12))


def _jitter_before_click(agent: "Agent"):
    pending = agent.current_session.get("pending_tool") or {}
    if not pending.get("name", "").startswith("click"):
        return
    browser = getattr(agent.tools, "browserautomation", None)
    if browser is None or getattr(browser, "page", None) is None:
        return
    try:
        browser._executor.submit(jitter, browser.page).result()
    except Exception as e:
        # Jitter is cosmetic; a mid-navigation page (viewport read throws) must not
        # block the click the agent actually asked for.
        agent.logger.print(f"[dim]human_jitter skipped: {e}[/dim]")


# Plugin is an event list. before_each_tool is the only hook between tool selection
# and tool execution, so it's where pre-click motion has to go.
human_jitter = [before_each_tool(_jitter_before_click)]
