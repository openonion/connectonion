"""Tools for watches created by the Agent in its current session."""


def _context(agent):
    store = getattr(agent, "_watch_store", None)
    session = agent.current_session or {}
    requester = session.get("requester") or {}
    if store is None or not session.get("session_id"):
        raise RuntimeError("Watches require a running session watch service")
    if requester.get("level") != "admin" or not requester.get("address"):
        raise PermissionError("Only the session owner can create or manage watches")
    return store, session["session_id"], requester["address"]


def watch_task(task_id: str, agent=None) -> dict:
    """Wake this session when a managed background task finishes or fails."""
    store, session_id, owner = _context(agent)
    return store.watch_task(session_id, owner, task_id)


def watch_every(minutes: int, probe: str, query: str = "",
                lifetime_hours: int = 168, agent=None) -> dict:
    """Check a read-only probe repeatedly and wake this session on changes.

    The first supported probe is gmail_search; query uses Gmail search syntax.
    A check with no new matches consumes no model turn.
    """
    store, session_id, owner = _context(agent)
    if probe != "gmail_search":
        raise ValueError("The available recurring probe is gmail_search")
    if not isinstance(minutes, int) or not 1 <= minutes <= 1440:
        raise ValueError("minutes must be between 1 and 1440")
    if not isinstance(lifetime_hours, int) or not 1 <= lifetime_hours <= 168:
        raise ValueError("lifetime_hours must be between 1 and 168")
    if not isinstance(query, str) or len(query) > 200:
        raise ValueError("query must be at most 200 characters")
    from ..session_watch import gmail_probe
    initial_ids = [item["id"] for item in gmail_probe(query)]
    return store.watch_every(session_id, owner, minutes=minutes, probe=probe,
                             query=query, lifetime_hours=lifetime_hours,
                             initial_ids=initial_ids)


def list_watches(agent=None) -> list[dict]:
    """List watches owned by this session."""
    store, session_id, owner = _context(agent)
    return store.list_watches(session_id, owner)


def cancel_watch(watch_id: str, agent=None) -> dict:
    """Stop one active watch in this session."""
    store, session_id, owner = _context(agent)
    return store.cancel(session_id, owner, watch_id)
