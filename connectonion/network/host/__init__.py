"""
Purpose: Host module re-exporting session, auth, routes, and server components for agent hosting
LLM-Note:
  Dependencies: imports from [session.py, auth.py, routes.py, server.py] | imported by [network/__init__.py, user code] | tested via integration tests
  Data flow: pure re-export module aggregating host functionality
  State/Effects: no state
  Integration: exposes host(agent, port, trust) main entry point, Session/SessionStorage for persistence, auth utilities (verify_signature, extract_and_authenticate, get_agent_address, is_custom_trust), route handlers (input_handler, session_handler, health_handler, info_handler, admin_*), create_app() ASGI factory, get_default_trust() helper
  Performance: trivial
  Errors: none
Host an agent over HTTP/WebSocket.
"""

from .session import Session, SessionStorage
from .auth import (
    verify_signature,
    extract_and_authenticate,
    get_agent_address,
    is_custom_trust,
    SIGNATURE_EXPIRY_SECONDS,
)
from .routes import (
    input_handler,
    session_handler,
    sessions_handler,
    health_handler,
    info_handler,
    admin_logs_handler,
    admin_sessions_handler,
)
from .server import (
    host,
    get_default_trust,
    create_app,
)

__all__ = [
    # Main entry point
    "host",
    # Session
    "Session",
    "SessionStorage",
    # Auth
    "verify_signature",
    "extract_and_authenticate",
    "get_agent_address",
    "is_custom_trust",
    "SIGNATURE_EXPIRY_SECONDS",
    # Routes
    "input_handler",
    "session_handler",
    "sessions_handler",
    "health_handler",
    "info_handler",
    "admin_logs_handler",
    "admin_sessions_handler",
    # Helpers
    "get_default_trust",
    "create_app",
]
