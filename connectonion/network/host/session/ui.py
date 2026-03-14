"""
Purpose: Convert session storage format to ChatItems wire format for frontend rendering
LLM-Note:
  Dependencies: imports from [] | imported by [routes.py, websocket.py, __init__.py] | tested by [tests/network/test_session_ui.py]
  Data flow: session dict {messages, trace} → ChatItem[] with types: user, agent, tool_call
  State/Effects: pure function, no side effects
  Integration: exposes session_to_chat_items(session) → list[dict] | used by routes.py, websocket.py OUTPUT messages
  Performance: O(n) where n = messages + trace entries
  Errors: none, handles missing keys with defaults

ChatItem types:
    - 'user': User message from messages[role='user']
    - 'agent': Agent response from messages[role='assistant']
    - 'tool_call': Tool execution from trace entries
"""


def session_to_chat_items(session: dict) -> list[dict]:
    """Convert session → ChatItem[] for UI rendering."""
    items = []

    # Messages → user/agent items
    for idx, msg in enumerate(session.get('messages', [])):
        role = msg.get('role', '')
        if role == 'user':
            items.append({'id': f"msg-{idx}", 'type': 'user', 'content': msg.get('content', '')})
        elif role == 'assistant':
            items.append({'id': f"msg-{idx}", 'type': 'agent', 'content': msg.get('content', '')})

    # Trace → tool_call items
    for idx, entry in enumerate(session.get('trace', [])):
        tool_name = entry.get('tool_name')
        if tool_name:
            status = 'error' if entry.get('status') == 'error' else 'running' if entry.get('status') == 'running' else 'done'
            items.append({
                'id': f"tool-{idx}",
                'type': 'tool_call',
                'name': tool_name,
                'args': entry.get('args'),
                'status': status,
                'result': entry.get('result'),
                'timing_ms': entry.get('timing_ms'),
            })

    return items
