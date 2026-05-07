"""
Purpose: Convert session storage format to ChatItems wire format for frontend rendering
LLM-Note:
  Dependencies: imports from [useful_plugins/interjection.py for INTERJECTION_FRAME_PREFIX] | imported by [host/http_router.py, host/ws_router.py, host/session/__init__.py] | tested by [tests/unit/test_host_session.py]
  Data flow: session dict {messages, trace} → ChatItem[] with types: user, agent, tool_call, files_received, intent, eval, thinking
  State/Effects: pure function, no side effects
  Integration: exposes session_to_chat_items(session) → list[dict] | used by http_router and ws_router when delivering server_newer state and OUTPUT
  Performance: O(n) where n = messages + trace entries
  Errors: none, handles missing keys with defaults

ChatItem types reconstructed:
    - 'user' / 'agent': from messages[role='user'|'assistant']
    - 'tool_call': from trace entries with tool_name
    - 'files_received': from trace entries with type='files_received'
    - 'intent': from trace entries with type='intent' (final 'understood' state)
    - 'eval': from trace entries with type='eval' (final 'done' state)
    - 'thinking': from trace entries with type='thinking' (re_act / reflect plugins)

Streaming-only event types (llm_call, llm_result, compact, etc.) are not
reconstructed — they're live-only feedback and don't survive reconnect by design.
"""

from ....useful_plugins.interjection import INTERJECTION_FRAME_PREFIX


def _trace_entry_to_item(entry: dict, idx: int) -> dict | None:
    """Map a single trace entry to a ChatItem. Returns None if the entry has no UI."""
    entry_type = entry.get('type')

    if entry_type == 'files_received':
        return {
            'id': f"files-{idx}",
            'type': 'files_received',
            'files': entry.get('files', []),
        }

    if entry_type == 'intent':
        return {
            'id': entry.get('id') or f"intent-{idx}",
            'type': 'intent',
            'status': 'understood',
            'ack': entry.get('ack'),
            'is_build': entry.get('is_build'),
        }

    if entry_type == 'eval':
        return {
            'id': entry.get('id') or f"eval-{idx}",
            'type': 'eval',
            'status': 'done',
            'passed': entry.get('passed'),
            'summary': entry.get('summary'),
            'expected': entry.get('expected'),
            'eval_path': entry.get('eval_path'),
        }

    if entry_type == 'thinking':
        return {
            'id': entry.get('id') or f"thinking-{idx}",
            'type': 'thinking',
            'status': 'done',
            'content': entry.get('content'),
            'kind': entry.get('kind'),
        }

    # tool_executor.py records two trace entries per tool: 'tool_call' (placeholder before
    # execute, no result) then 'tool_result' (final state, has status/result/timing_ms).
    # Emit one ChatItem per tool from the 'tool_result' so we don't double-render. Match
    # client tool_id keying so live and replayed items share an identity.
    if entry_type == 'tool_result':
        name = entry.get('name')
        if not name:
            return None
        raw = entry.get('status', 'done')
        if raw in ('error', 'not_found'):
            ui_status = 'error'
        elif raw == 'running':
            ui_status = 'running'
        else:
            ui_status = 'done'
        return {
            'id': entry.get('tool_id') or f"tool-{idx}",
            'type': 'tool_call',
            'name': name,
            'args': entry.get('args'),
            'status': ui_status,
            'result': entry.get('result'),
            'timing_ms': entry.get('timing_ms'),
        }

    return None


def session_to_chat_items(session: dict) -> list[dict]:
    """Convert session → ChatItem[] for UI rendering, interleaved chronologically by turn.

    Order within a turn: user message → trace entries (intent, tool_call, eval, thinking, ...)
    → final assistant message. Turn boundaries are detected from `user_input` markers in
    trace; a fallback path is used if those markers are missing (older sessions).
    """
    messages = session.get('messages', [])
    trace = session.get('trace', [])

    # Group trace entries by turn boundary (user_input markers).
    # turns[k] = list of (idx, entry) tuples for trace entries belonging to turn k.
    turns: list[list[tuple[int, dict]]] = []
    current: list[tuple[int, dict]] = []
    for idx, entry in enumerate(trace):
        if entry.get('type') == 'user_input':
            turns.append(current)
            current = []
        else:
            current.append((idx, entry))
    turns.append(current)
    # turns[0] = entries before first user_input (usually empty);
    # turns[1..] = entries within each turn.

    # Walk messages: emit user, then that turn's trace items, then assistant.
    items: list[dict] = []
    user_count = 0
    for msg_idx, msg in enumerate(messages):
        role = msg.get('role', '')
        if role == 'user':
            content = msg.get('content', '')
            if isinstance(content, str) and content.startswith(INTERJECTION_FRAME_PREFIX):
                content = content[len(INTERJECTION_FRAME_PREFIX):]
            items.append({'id': f"msg-{msg_idx}", 'type': 'user', 'content': content})
            user_count += 1
            # Trace bucket for this turn lives at index user_count (turns[0] holds pre-turn entries).
            if user_count < len(turns):
                for trace_idx, entry in turns[user_count]:
                    item = _trace_entry_to_item(entry, trace_idx)
                    if item:
                        items.append(item)
        elif role == 'assistant' and msg.get('content'):
            items.append({'id': f"msg-{msg_idx}", 'type': 'agent', 'content': msg.get('content', '')})

    # Fallback: if no user_input markers found in trace, append all remaining trace
    # entries at the end so the data isn't silently dropped (older sessions).
    if len(turns) == 1 and turns[0]:
        for trace_idx, entry in turns[0]:
            item = _trace_entry_to_item(entry, trace_idx)
            if item:
                items.append(item)

    return items
