"""
Session management package for hosted agents.

Exports:
    - Session, SessionStorage: Persistent storage (JSONL)
    - ActiveSession, ActiveSessionRegistry: Runtime registry for reconnection
    - merge_sessions: Conflict resolution between client/server state
    - session_to_chat_items: Convert storage format to UI format
    - start_cleanup_job: Background cleanup thread
"""

from .storage import Session, SessionStorage
from .active import ActiveSession, ActiveSessionRegistry, start_cleanup_job
from .merge import merge_sessions
from .ui import session_to_chat_items

__all__ = [
    # Storage
    'Session',
    'SessionStorage',
    # Active sessions
    'ActiveSession',
    'ActiveSessionRegistry',
    'start_cleanup_job',
    # Utilities
    'merge_sessions',
    'session_to_chat_items',
]
