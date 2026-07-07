"""
LLM-Note: Bind-browser-session plugin.

Purpose: tell the shared BrowserAutomation which session (chat panel) the current
agent turn belongs to, so each session drives its own browser tab instead of all
sessions fighting over one page (A navigates and B's page jumps / closes).

Data flow: before_each_tool -> read agent.current_session['session_id'] -> hand it
to the BrowserAutomation instance via agent.tools.browserautomation._bind_session(),
which records it for the calling thread; the browser's dispatch decorator reads the
binding to route the call to that session's tab (creating it on first use).

Why before_each_tool: it fires on the agent's own thread right before each tool
runs — the same thread the browser dispatch decorator later reads the binding from.
Per-tool is cheap and keeps the binding correct across multi-turn sessions.

Why a plugin (not connectonion core): session routing stays opt-in and out of core.
It only matters when one BrowserAutomation is shared across concurrent hosted
sessions, so the agents that host a shared browser enable it (co ai, the
hosted-browser template, linkedin-agent-3), exactly like human_jitter. Agents
without it (or with no browser) are unaffected: the binding stays None and the
browser uses a single shared tab (original behaviour).

State/Effects: writes the per-thread binding on the browser instance; no agent or
module state. Best-effort — no browser tool or no session_id => no-op.
"""

from typing import TYPE_CHECKING

from ..core.events import before_each_tool

if TYPE_CHECKING:
    from ..core.agent import Agent


def _bind_browser_session(agent: "Agent") -> None:
    """Bind this turn's session to the agent's browser tool, if it has one.

    Named differently from BrowserAutomation._bind_session on purpose: this is
    the event handler that reads the session off the agent; that is the browser
    method that records it.
    """
    browser = getattr(agent.tools, "browserautomation", None)
    if browser is None:
        return
    session_id = (agent.current_session or {}).get("session_id")
    browser._bind_session(session_id)


# Plugin is an event list. before_each_tool runs on the agent thread just before a
# tool executes, which is where the browser dispatch decorator reads the binding.
bind_browser_session = [before_each_tool(_bind_browser_session)]
