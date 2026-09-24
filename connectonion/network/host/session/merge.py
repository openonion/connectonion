"""
Purpose: Session merge logic for resolving client/server state conflicts on reconnection
LLM-Note:
  Dependencies: imports from [] | imported by [host/http_router.py, host/ws_router/connect.py, host/session/__init__.py] | tested by [tests/unit/test_session_merge.py]
  Data flow: client_session dict + server_session dict → compare iteration counts → return (winner, server_won: bool)
  State/Effects: pure function, no side effects
  Integration: exposes merge_sessions(client, server) → (merged, server_won) | used by http_router.input_handler and ws_router.connect.handle_connect on reconnection
  Performance: O(1) dict access
  Errors: none, handles missing keys with defaults

Strategy — compare (turn, iteration, updated), first difference wins:
    1. turn: increments once per INPUT and never resets, so it orders sessions
    2. iteration: increments each LLM call but restarts at 0 every turn, so it
       only orders two copies of the *same* turn (mid-turn detection)
    3. updated timestamp as the last tiebreaker; fully equal keeps the client

Comparing iteration alone let a device whose last turn made 7 LLM calls
overwrite a newer turn another device ran in 2, erasing it (#1606).
"""


def _version(session: dict) -> tuple:
    return (session.get('turn', 0), session.get('iteration', 0), session.get('updated', 0))


def merge_sessions(client_session: dict, server_session: dict) -> tuple[dict, bool]:
    """
    Merge two sessions, return (merged_session, server_won).
    """
    if _version(server_session) > _version(client_session):
        return server_session, True
    return client_session, False
