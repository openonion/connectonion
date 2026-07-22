"""
Purpose: Public surface for the host-side session subsystem — bundles persistent JSONL storage, the runtime registry of active sessions, the merge resolver, and the UI projection helper into one import.
LLM-Note:
  Dependencies: re-exports from [.storage (Session, SessionStorage), .active (ActiveSession, ActiveSessionRegistry, start_cleanup_job), .merge (merge_sessions), .ui (session_to_chat_items)] | imported by [network/host/__init__.py, network/host/server.py, network/host/http_router.py, network/host/ws_router/connect.py (lazy), network/host/ws_router/agent_io.py (lazy)] | tested via the individual submodule tests (tests/network/test_session_storage.py, test_session_merge.py, tests/unit/test_host_session.py)
  Data flow: aggregator only — no logic of its own. Submodules: storage persists Session JSONL to disk; active tracks live websocket sessions; merge resolves client/server divergence; ui converts storage rows to chat items
  State/Effects: none directly; submodules touch the filesystem (storage) and spawn a cleanup thread (active.start_cleanup_job)
  Integration: exposes Session, SessionStorage, ActiveSession, ActiveSessionRegistry, start_cleanup_job, merge_sessions, session_to_chat_items
"""

from .storage import Session, SessionStorage, narrow_server_state
from .active import ActiveSession, ActiveSessionRegistry, start_cleanup_job
from .merge import merge_sessions
from .ui import session_to_chat_items

__all__ = [
    # Storage
    'Session',
    'SessionStorage',
    'narrow_server_state',
    # Active sessions
    'ActiveSession',
    'ActiveSessionRegistry',
    'start_cleanup_job',
    # Utilities
    'merge_sessions',
    'session_to_chat_items',
]
