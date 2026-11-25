"""
Purpose: Decide when a requester lost access, and stop their running turn when they did
LLM-Note:
  Dependencies: imports from [rich.console] | imported by [.server (installs the step check on every hosted Agent), .ws_router.connect, .ws_router.session (per-frame socket check)]
  Data flow: trust_agent lists → current_trust_level → lost_access(granted level) | stop_turn_when_revoked → before_llm / before_each_tool handler → io.request_interrupt() (or PermissionError without an io)
  State/Effects: reads trust files on each check | prints one operator line when a turn is stopped | requests an interrupt on the turn's io
  Integration: the socket check covers a connected requester between frames; this step check covers a requester who has disconnected
  Errors: PermissionError when the turn has no interrupt mailbox (HTTP /input)
"""
from rich.console import Console

REVOKED = "Your access to this agent was revoked by its admin."
# Handoffs only permits handoff messages; it grants no tool access to revoke.
TRUST_GRANTS = {"admin": 3, "whitelist": 2, "contact": 1}


def current_trust_level(trust_agent, address):
    """Read live list membership, with an explicit block taking precedence."""
    level = trust_agent.get_level(address)
    if level == "blocked":
        return level
    return "admin" if trust_agent.is_admin(address) else level


def lost_access(trust_agent, address, granted):
    """Return (revoked, level): blocked, or now holding less than `granted`."""
    level = current_trust_level(trust_agent, address)
    revoked = level == "blocked" or TRUST_GRANTS.get(level, 0) < TRUST_GRANTS.get(granted, 0)
    return revoked, level


def stop_turn_when_revoked(trust_agent):
    """An event handler that re-checks the requester before each tool or model step."""
    def check(agent):
        requester = agent.current_session.get("requester") or {}
        address = requester.get("address")
        if not address or not lost_access(trust_agent, address, requester.get("level"))[0]:
            return
        Console().print(f"Host: stopped the running turn of {address}; their access was revoked.",
                        markup=False, soft_wrap=True)
        if agent.io is None:
            raise PermissionError(REVOKED)
        # The step that fires this event takes the interrupt before it starts.
        agent.io.request_interrupt()
    return check
