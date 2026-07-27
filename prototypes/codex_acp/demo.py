"""
PROTOTYPE demo — drive the fake codex-acp agent through the ACP client and
show how session/update maps onto ConnectOnion's io event model.

Run:  python prototypes/codex_acp/demo.py

Against the real adapter you'd swap the command for
["npx", "-y", "@zed-industries/codex-acp"] (or a local codex-acp binary);
nothing else changes.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from acp_client import ACPClient


def main():
    fake_agent = [sys.executable, os.path.join(os.path.dirname(__file__), "fake_codex_acp.py")]

    # on_event is what the ConnectOnion tool would forward to agent.io.log(...)
    def on_event(event):
        kind = event["acp_update"]
        if kind in ("agent_message_chunk", "agent_thought_chunk"):
            print(f"  [io] {kind:22} text={event['text']!r}")
        elif kind in ("tool_call", "tool_call_update"):
            print(f"  [io] {kind:22} {event.get('title','') or event['tool_call_id']} "
                  f"status={event.get('status','')}")
        else:
            print(f"  [io] {kind:22} {event}")

    # on_permission is what would become agent.io.request_approval(...)
    def on_permission(tool_call, options):
        print(f"  [PERMISSION] agent wants to: {tool_call.get('title')!r}")
        choice = options[0]["optionId"]  # auto-allow for the demo
        print(f"  [PERMISSION] -> answering {choice!r}")
        return choice

    client = ACPClient(command=fake_agent, cwd=".", on_event=on_event, on_permission=on_permission)
    client.start()

    print("=== initialize ===")
    info = client.initialize()
    print(f"  agent: {info.get('agentInfo')}  caps: {info.get('agentCapabilities')}")

    print("=== session/new ===")
    session_id = client.new_session()
    print(f"  sessionId: {session_id}")

    print("=== session/prompt (streaming) ===")
    stop = client.prompt(session_id, "fix the failing tests")
    print(f"=== turn ended: stopReason={stop!r} ===")

    print("=== session/load (resume same session) ===")
    resumed = client.load_session(session_id)
    print(f"  resumed sessionId: {resumed}")

    client.close()


if __name__ == "__main__":
    main()
