"""
LLM-Note: Bind-browser-session plugin.

Purpose: tell the shared BrowserAutomation which session (chat panel) the current
agent turn belongs to, so each session drives its own browser tab instead of all
sessions fighting over one page (A navigates and B's page jumps / closes).

Data flow: before_each_tool -> read agent.current_session['session_id'] -> hand it
to the BrowserAutomation instance via agent.tools.browserautomation._bind_session(),
which stashes it in a thread-local that the browser's dispatch decorator reads to
route the call to that session's tab (creating it on first use).

Why before_each_tool: it fires on the agent's own thread right before each tool
runs — the same thread the browser dispatch decorator later reads the binding from.
Per-tool is cheap and keeps the binding correct across multi-turn sessions.

Why a plugin (not connectonion core): session routing stays opt-in and out of core —
an agent enables multi-tab isolation by adding this to plugins, exactly like
human_jitter. Agents without it (or with no browser) are unaffected: the key stays
None and the browser uses a single shared tab (original behaviour).

State/Effects: writes a thread-local on the agent thread; no agent state. Best-effort
— if there is no browser tool or no session_id, it does nothing.
"""

from typing import TYPE_CHECKING

from ..core.events import before_each_tool

if TYPE_CHECKING:
    from ..core.agent import Agent


def _bind_session(agent: "Agent") -> None:
    browser = getattr(agent.tools, "browserautomation", None)
    if browser is None:
        return
    session_id = (agent.current_session or {}).get("session_id")
    browser._bind_session(session_id)


# Plugin is an event list. before_each_tool runs on the agent thread just before a
# tool executes, which is where the browser dispatch decorator reads the binding.
bind_browser_session = [before_each_tool(_bind_session)]
