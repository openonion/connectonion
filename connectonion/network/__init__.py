"""Network layer for hosting and connecting agents.

This module contains:
- host: Host an agent over HTTP/WebSocket
- asgi: ASGI app implementation
- relay: Agent relay server for P2P discovery
- connect: Multi-agent networking (RemoteAgent)
- announce: Service announcement protocol
- trust: Trust verification system
"""

from .host import host, create_app, SessionStorage, Session
from .connect import connect, RemoteAgent
from .relay import connect as relay_connect, serve_loop
from .announce import create_announce_message
from .trust import create_trust_agent, get_default_trust_level, TRUST_LEVELS
from . import relay, announce

__all__ = [
    "host",
    "create_app",
    "SessionStorage",
    "Session",
    "connect",
    "RemoteAgent",
    "relay_connect",
    "serve_loop",
    "create_announce_message",
    "create_trust_agent",
    "get_default_trust_level",
    "TRUST_LEVELS",
    "relay",
    "announce",
]
