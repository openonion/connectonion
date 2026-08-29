"""
Purpose: Network layer package re-exporting host, IO, asgi, relay, connect, announce, trust modules
LLM-Note:
  Dependencies: imports from [host/, io/, connect.py, relay.py, announce.py, trust/] | imported by [__init__.py main package, user code] | tested via submodule tests
  Data flow: pure re-export module aggregating networking functionality
  State/Effects: no state
  Integration: exposes host(agent, port, trust), create_app(), IO/WebSocketIO, SessionStorage/Session, connect(url), RemoteAgent, Response, PermissionModeError, relay server (relay_connect, serve_loop), announce (create_announce_message), trust (TrustAgent) | unified networking API surface
  Performance: trivial
  Errors: none
Network layer for hosting and connecting agents.

This module contains:
- host: Host an agent over HTTP/WebSocket
- IO: Base class for agent-client communication
- asgi: ASGI app implementation
- relay: Agent relay server for P2P discovery
- connect: Multi-agent networking (RemoteAgent)
- announce: Service announcement protocol
- trust: Trust verification system (TrustAgent is the single interface)
"""

from . import announce, relay
from .announce import create_announce_message
from .connect import ExecResult, PermissionModeError, RemoteAgent, Response, connect
from .host import (
    HTTPRequest,
    HTTPResponse,
    HTTPRoute,
    HTTPRouter,
    Session,
    SessionStorage,
    create_app,
    host,
)
from .io import IO, WebSocketIO
from .relay import connect as relay_connect
from .relay import serve_loop
from .trust import TRUST_LEVELS, Decision, TrustAgent, parse_policy

__all__ = [
    "host",
    "create_app",
    "IO",
    "WebSocketIO",
    "SessionStorage",
    "Session",
    "connect",
    "RemoteAgent",
    "Response",
    "ExecResult",
    "PermissionModeError",
    "HTTPRequest",
    "HTTPResponse",
    "HTTPRoute",
    "HTTPRouter",
    "relay_connect",
    "serve_loop",
    "create_announce_message",
    # Trust (TrustAgent is the single interface)
    "TrustAgent",
    "Decision",
    "TRUST_LEVELS",
    "parse_policy",
    "relay",
    "announce",
]
