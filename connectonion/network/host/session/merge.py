"""
Purpose: Session merge logic for resolving client/server state conflicts on reconnection
LLM-Note:
  Dependencies: imports from [] | imported by [routes.py, websocket.py, __init__.py] | tested by [tests/network/test_session_merge.py]
  Data flow: client_session dict + server_session dict → compare iteration counts → return (winner, server_won: bool)
  State/Effects: pure function, no side effects
  Integration: exposes merge_sessions(client, server) → (merged, server_won) | used by routes.py input_handler, websocket.py reconnection
  Performance: O(1) dict access
  Errors: none, handles missing keys with defaults

Strategy:
    1. Compare iteration counts (increments each LLM call, more granular than turn)
    2. Higher iteration wins (server continued while client was disconnected)
    3. If equal, compare updated timestamps as tiebreaker
"""


def merge_sessions(client_session: dict, server_session: dict) -> tuple[dict, bool]:
    """
    Merge two sessions, return (merged_session, server_won).

    Uses iteration count (increments each LLM call) for granular mid-turn detection.
    Falls back to timestamp if iterations are equal.
    """
    client_iter = client_session.get('iteration', 0)
    server_iter = server_session.get('iteration', 0)

    if server_iter > client_iter:
        return server_session, True
    elif client_iter > server_iter:
        return client_session, False
    else:
        # Tiebreaker: timestamp
        client_updated = client_session.get('updated', 0)
        server_updated = server_session.get('updated', 0)
        if server_updated > client_updated:
            return server_session, True
        return client_session, False
