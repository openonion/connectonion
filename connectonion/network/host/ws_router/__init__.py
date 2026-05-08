"""
Purpose: WebSocket message router package — single message-handling implementation shared by direct ASGI WebSocket and relay-routed paths
LLM-Note:
  Dependencies: re-exports from .session | imported by [network/host/server.py, network/asgi/websocket.py, network/relay.py via session_handler partial] | tested by [tests/unit/test_asgi.py]
  Data flow: send_msg/recv_msg adapter pair → run_session → per-type dispatch → handle_connect / start_agent / inline branches | runtime input on existing running session → push_runtime_input + RUNTIME_INPUT_ACK | cleanup cancels forward + ping tasks
  State/Effects: no module-level state | session-scoped state lives inside run_session (conn dict + active_io + forward_task + ping_task local vars)
  Integration: exposes run_session(send_msg, recv_msg, *, route_handlers, storage, registry, trust, ...) | the only public API of this package; callers should not import private modules directly
  Performance: O(1) per-message dispatch | one forward_task + one ping_task per session
  Errors: agent thread exceptions captured in result_holder, surfaced as ERROR frame; transport adapters surface client-close via recv_msg → None

run_session() drives one client session from connect to disconnect:
read messages → dispatch by type → cleanup on close. run_session is the
single reader of recv_msg — no other function touches it.
"""

from .session import run_session

__all__ = ["run_session"]
