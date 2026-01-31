"""
Purpose: Network layer package re-exporting host, IO, asgi, relay, connect, announce, trust modules
LLM-Note:
  Dependencies: imports from [host/, io/, connect.py, relay.py, announce.py, trust/] | imported by [__init__.py main package, user code] | tested via submodule tests
  Data flow: pure re-export module aggregating networking functionality
  State/Effects: no state
  Integration: exposes host(agent, port, trust), create_app(), IO/WebSocketIO, SessionStorage/Session, connect(url), RemoteAgent, Response, relay server (relay_connect, serve_loop), announce (create_announce_message), trust (create_trust_agent, TRUST_LEVELS, prompts) | unified networking API surface
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
- trust: Trust verification system
"""

from .host import host, create_app, SessionStorage, Session
from .io import IO, WebSocketIO
from .connect import connect, RemoteAgent, Response
from .relay import connect as relay_connect, serve_loop
from .announce import create_announce_message
from .trust import create_trust_agent, get_default_trust_level, TRUST_LEVELS, get_trust_prompt, TRUST_PROMPTS
from . import relay, announce

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
    "relay_connect",
    "serve_loop",
    "create_announce_message",
    "create_trust_agent",
    "get_default_trust_level",
    "TRUST_LEVELS",
    "get_trust_prompt",
    "TRUST_PROMPTS",
    "relay",
    "announce",
]
