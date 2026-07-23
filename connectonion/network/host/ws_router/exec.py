"""
Purpose: Handle the EXEC message — direct tool execution bypassing the LLM loop
LLM-Note:
  Dependencies: imports from [asyncio, rich.console] | imported by [.session as part of EXEC dispatch] | tested by [tests/unit/test_ws_exec.py]
  Data flow: run_exec(data, send_msg, route_handlers) → validate tool name → route_handlers["ws_exec"](tool, args) in a worker thread (blocking tools must not stall the WS read loop) → EXEC_RESULT frame {exec_id, tool, status, result|error, duration_ms}
  State/Effects: no state | spawned as an asyncio Task per EXEC by session.py so pipelined EXECs run concurrently
  Integration: run_exec(data, send_msg, route_handlers) — data is the raw EXEC frame {type, exec_id, tool, args} | session.py gates on conn["authenticated"] before dispatching here
  Performance: one asyncio.to_thread per EXEC | no session storage, no registry — stateless request/response
  Errors: missing tool name and handler exceptions both surface as EXEC_RESULT status=error (a background task's raise would be invisible to the client, which would hang until timeout)
"""
import asyncio

from rich.console import Console

console = Console()


async def run_exec(data, send_msg, route_handlers):
    """Run one EXEC request in a worker thread, reply with EXEC_RESULT."""
    exec_id = data.get("exec_id")
    tool_name = data.get("tool")
    args = data.get("args") or {}

    if not tool_name:
        await send_msg({"type": "EXEC_RESULT", "exec_id": exec_id,
                        "status": "error", "error": "tool required"})
        return

    console.print(f"[green]✓ EXEC[/green] tool={tool_name} args={str(args)[:80]}")
    try:
        result = await asyncio.to_thread(route_handlers["ws_exec"], tool_name, args)
    except Exception as e:
        result = {"status": "error", "error": f"{type(e).__name__}: {e}"}

    await send_msg({"type": "EXEC_RESULT", "exec_id": exec_id, "tool": tool_name, **result})
