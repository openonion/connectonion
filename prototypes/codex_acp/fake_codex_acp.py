"""
PROTOTYPE — a fake ACP *Agent* that mimics codex-acp's server side.

Lets us validate the ACPClient end-to-end without installing the real
codex-acp binary. Speaks newline-delimited JSON-RPC on stdin/stdout and
emits a realistic session/update stream for one prompt, including a
session/request_permission round-trip (the part headless codex exec lacks).

Run indirectly: ACPClient(command=[sys.executable, "fake_codex_acp.py"]).
"""

import json
import sys

SESSION_ID = "acp-thread-abc123"


def send(msg):
    sys.stdout.write(json.dumps(msg) + "\n")
    sys.stdout.flush()


def notify_update(update):
    send({"jsonrpc": "2.0", "method": "session/update",
          "params": {"sessionId": SESSION_ID, "update": update}})


def log(text):
    sys.stderr.write(text + "\n")
    sys.stderr.flush()


def run_prompt():
    # 1. streamed assistant text
    notify_update({"sessionUpdate": "agent_message_chunk",
                   "content": {"type": "text", "text": "Looking at the failing tests…"}})
    # 2. a tool call starts (Codex is about to run a command)
    notify_update({"sessionUpdate": "tool_call", "toolCallId": "call-1",
                   "title": "Run `pytest -q`", "kind": "execute", "status": "pending"})
    # 3. ask the client for permission to run it
    perm_id = 1000
    send({"jsonrpc": "2.0", "id": perm_id, "method": "session/request_permission",
          "params": {"sessionId": SESSION_ID,
                     "toolCall": {"toolCallId": "call-1", "title": "Run `pytest -q`"},
                     "options": [
                         {"optionId": "allow-once", "name": "Allow", "kind": "allow_once"},
                         {"optionId": "reject", "name": "Reject", "kind": "reject_once"},
                     ]}})
    return perm_id


def main():
    pending_perm = None
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        msg = json.loads(line)
        method = msg.get("method")
        msg_id = msg.get("id")

        if method == "initialize":
            send({"jsonrpc": "2.0", "id": msg_id, "result": {
                "protocolVersion": 1,
                "agentCapabilities": {"loadSession": True},
                "agentInfo": {"name": "fake-codex-acp", "version": "0.0.1"},
            }})
        elif method == "session/new":
            send({"jsonrpc": "2.0", "id": msg_id, "result": {"sessionId": SESSION_ID}})
        elif method == "session/load":
            send({"jsonrpc": "2.0", "id": msg_id, "result": {}})
        elif method == "session/prompt":
            pending_perm = run_prompt()
            # session/prompt response is deferred until after the permission reply.
            globals()["_prompt_id"] = msg_id
        elif method is None and msg_id == pending_perm:
            # client answered our permission request
            outcome = msg.get("result", {}).get("outcome", {})
            allowed = outcome.get("optionId") == "allow-once"
            status = "completed" if allowed else "failed"
            notify_update({"sessionUpdate": "tool_call_update", "toolCallId": "call-1",
                           "status": status})
            notify_update({"sessionUpdate": "agent_message_chunk",
                           "content": {"type": "text",
                                       "text": "All tests pass now." if allowed else "Skipped: not permitted."}})
            send({"jsonrpc": "2.0", "id": globals()["_prompt_id"],
                  "result": {"stopReason": "end_turn"}})
        else:
            if msg_id is not None:
                send({"jsonrpc": "2.0", "id": msg_id,
                      "error": {"code": -32601, "message": f"unknown: {method}"}})


if __name__ == "__main__":
    main()
