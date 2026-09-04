"""
Purpose: Convert session storage format to ChatItems wire format for frontend rendering
LLM-Note:
  Dependencies: imports from [useful_plugins/runtime_input.py for RUNTIME_INPUT_FRAME_PREFIX] | imported by [host/http_router.py, host/ws_router/agent_io.py, host/ws_router/connect.py, host/session/__init__.py] | tested by [tests/unit/test_host_session.py]
  Data flow: session dict {messages, trace} → ChatItem[] with types: user, agent, tool_call, files_received, intent, eval, thinking | persisted assistant message IDs survive reconstruction; legacy messages fall back to their index
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

from ....core.provider_events import provider_artifact_event, provider_message_event
from ....useful_plugins.runtime_input import RUNTIME_INPUT_FRAME_PREFIX


def _trace_entry_to_item_ui(entry: dict, idx: int) -> dict | None:
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

    if entry_type == 'provider_invocation':
        return {
            key: value for key, value in entry.items()
            if key not in {'ts'}
        }

    if entry_type == 'provider_activity':
        return _provider_activity_item(entry)

    if entry_type == 'provider_artifact':
        return _provider_artifact_item(entry)

    if entry_type == 'provider_message':
        return _provider_message_item(entry)

    # tool_executor.py records two trace entries per tool: 'tool_call' (placeholder before
    # execute, no result) then 'tool_result' (final state, has status/result/timing_ms).
    # Emit one ChatItem per tool from the 'tool_result' so we don't double-render. Match
    # client tool_id keying so live and replayed items share an identity.
    if entry_type == 'tool_result':
        name = entry.get('name')
        if not name:
            return None
        raw = entry.get('status')
        # A tool_result is terminal. Only known success values render as done;
        # missing, start-only, and unknown statuses fail closed as errors.
        ui_status = (
            'done' if raw in ('success', 'done', 'completed') else 'error'
        )
        item = {
            'id': entry.get('tool_id') or f"tool-{idx}",
            'type': 'tool_call',
            'name': name,
            'args': entry.get('args'),
            'status': ui_status,
            'result': entry.get('result'),
            'timing_ms': entry.get('timing_ms'),
        }
        if isinstance(entry.get('summary'), str) and entry['summary']:
            item['summary'] = entry['summary']
        for key in ('provider', 'invocationId', 'parentToolCallId'):
            if key in entry:
                item[key] = entry[key]
        return item

    return None


def _provider_activity_item(entry: dict) -> dict | None:
    """Keep only the safe typed Work Room fields during replay."""
    activity_id = entry.get('activityId')
    invocation_id = entry.get('invocationId')
    parent_id = entry.get('parentToolCallId')
    if not all(isinstance(value, str) and value for value in (activity_id, invocation_id, parent_id)):
        return None
    sequence = entry.get('sequence')
    if isinstance(sequence, bool) or not isinstance(sequence, int) or sequence < 1:
        return None
    kind = entry.get('kind')
    status = entry.get('status')
    title = entry.get('title')
    summary = entry.get('summary')
    if not all(isinstance(value, str) and value for value in (kind, status, title, summary)):
        return None
    item = {
        'type': 'provider_activity',
        'invocationId': invocation_id,
        'parentToolCallId': parent_id,
        'activityId': activity_id,
        'sequence': sequence,
        'kind': kind,
        'status': status,
        'title': title,
        'summary': summary,
    }
    files = _safe_file_names(entry.get('files'))
    if files:
        item['files'] = files
    return item


def _provider_artifact_item(entry: dict) -> dict | None:
    """Revalidate a persisted preview with Core's canonical strict contract."""
    artifact_id = entry.get('artifactId')
    invocation_id = entry.get('invocationId')
    parent_id = entry.get('parentToolCallId')
    thumbnail = entry.get('thumbnailDataUrl')
    alt = entry.get('alt')
    revision = entry.get('stateRevision')
    if not all(
        isinstance(value, str) and value
        for value in (artifact_id, invocation_id, parent_id, thumbnail, alt)
    ):
        return None
    if entry.get('kind') != 'screenshot':
        return None
    try:
        return provider_artifact_event(
            provider=entry.get('provider'),
            invocation_id=invocation_id,
            parent_tool_call_id=parent_id,
            artifact_id=artifact_id,
            state_revision=revision,
            thumbnail_data_url=thumbnail,
            alt=alt,
        )
    except ValueError:
        return None


def _provider_message_item(entry: dict) -> dict | None:
    """Replay only bounded, plain-text direct provider conversation content."""
    try:
        return provider_message_event(
            provider=entry.get('provider'),
            invocation_id=entry.get('invocationId'),
            parent_tool_call_id=entry.get('parentToolCallId'),
            message_id=entry.get('messageId'),
            role=entry.get('role'),
            text=entry.get('text'),
            **({"workroom_id": entry["workroomId"]} if "workroomId" in entry else {}),
            **({"continuation_of": entry["continuationOf"]} if "continuationOf" in entry else {}),
        )
    except ValueError:
        return None


def _safe_file_names(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    names: list[str] = []
    for candidate in value[:8]:
        if not isinstance(candidate, str):
            continue
        name = candidate.replace('\\', '/').rstrip('/').rsplit('/', 1)[-1]
        if name and name not in {'.', '..'} and name not in names:
            names.append(name[:128])
    return names


def session_to_chat_items(session: dict) -> list[dict]:
    """Convert session → ChatItem[] for UI rendering, interleaved chronologically by turn.

    Order within a turn: user message → trace entries (intent, tool_call, eval, thinking, ...)
    → final assistant message. Turn boundaries are detected from `user_input` markers in
    trace; a fallback path is used if those markers are missing (older sessions).
    """
    messages = session.get('messages', [])
    trace = session.get('trace', [])

    # Group trace entries by turn boundary (user_input markers).
    # turn_entries[k] = list of (idx, entry) tuples for trace entries belonging to turn k.
    turn_entries: list[list[tuple[int, dict]]] = []
    current_msgs: list[tuple[int, dict]] = []
    for idx, entry in enumerate(trace):
        if entry.get('type') == 'user_input':
            turn_entries.append(current_msgs)
            current_msgs = []
        else:
            current_msgs.append((idx, entry))
    turn_entries.append(current_msgs)
    # turn_entries[0] = entries before first user_input (usually empty);
    # turn_entries[1..] = entries within each turn.

    # Walk messages: emit user, then that turn's trace items, then assistant.
    items_ui: list[dict] = []
    user_count = 0
    for msg_idx, msg in enumerate(messages):
        role = msg.get('role', '')
        if role == 'user':
            content = msg.get('content', '')
            if isinstance(content, str) and content.startswith(RUNTIME_INPUT_FRAME_PREFIX):
                content = content[len(RUNTIME_INPUT_FRAME_PREFIX):]

            # Structural, not a regex over content: a message the system injected
            # carries `internal`, and a user who literally types
            # "<system-reminder>" must see their own words back unchanged.
            if not msg.get('internal'):
                items_ui.append({'id': f"msg-{msg_idx}", 'type': 'user', 'content': content})

            # Counted either way. The bubble is suppressed; the TURN is not — an
            # internal message still opened one, and skipping the increment drops
            # every tool call that turn made from the transcript. That is the
            # regression #144's first cut shipped.
            user_count += 1
            if user_count < len(turn_entries):
                for trace_idx, entry in turn_entries[user_count]:
                    item_ui = _trace_entry_to_item_ui(entry, trace_idx)
                    if item_ui:
                        items_ui.append(item_ui)
        elif role == 'assistant' and msg.get('content'):
            message_id = msg.get('id')
            if not isinstance(message_id, str) or not message_id:
                message_id = f"msg-{msg_idx}"
            items_ui.append({
                'id': message_id,
                'type': 'agent',
                'content': msg.get('content', ''),
            })

    # Fallback: if no user_input markers found in trace, append all remaining trace
    # entries at the end so the data isn't silently dropped (older sessions).
    if len(turn_entries) == 1 and turn_entries[0]:
        for trace_idx, entry in turn_entries[0]:
            item_ui = _trace_entry_to_item_ui(entry, trace_idx)
            if item_ui:
                items_ui.append(item_ui)

    return _nest_provider_invocations(items_ui)


def _nest_provider_invocations(items: list[dict]) -> list[dict]:
    """Rebuild the same single provider card produced by the live mapper."""
    invocations: dict[str, dict] = {}
    parent_ids: set[str] = set()
    for item in items:
        if item.get('type') != 'provider_invocation':
            continue
        invocation_id = item.get('invocationId') or item.get('id')
        parent_id = item.get('parentToolCallId')
        if not isinstance(invocation_id, str) or not isinstance(parent_id, str):
            continue
        parent_ids.add(parent_id)
        existing = invocations.get(invocation_id)
        if existing is None:
            existing = {**item, 'id': invocation_id, 'activities': []}
            invocations[invocation_id] = existing
        else:
            activities = existing['activities']
            messages = existing.get('messages')
            existing.update(item)
            existing['id'] = invocation_id
            existing['activities'] = activities
            if messages:
                existing['messages'] = messages

    if not invocations:
        return items

    native_activity_ids = {
        (item.get('invocationId'), item.get('activityId'))
        for item in items
        if (
            item.get('type') == 'provider_activity'
            and item.get('invocationId') in invocations
            and isinstance(item.get('activityId'), str)
        )
    }

    output: list[dict] = []
    emitted: set[str] = set()
    for item in items:
        invocation_id = item.get('invocationId')
        parent_id = item.get('parentToolCallId')
        if item.get('type') == 'provider_invocation' and invocation_id in invocations:
            if invocation_id not in emitted:
                output.append(invocations[invocation_id])
                emitted.add(invocation_id)
            continue
        if (
            item.get('type') == 'provider_message'
            and isinstance(invocation_id, str)
            and invocation_id in invocations
        ):
            message = _nested_provider_message(item)
            if message:
                _upsert_provider_message(invocations[invocation_id], message)
            continue
        if (
            item.get('type') == 'provider_artifact'
            and isinstance(invocation_id, str)
            and invocation_id in invocations
        ):
            artifact = _nested_provider_artifact(item)
            invocation = invocations[invocation_id]
            if (
                artifact
                and artifact['stateRevision'] == invocation.get('stateRevision')
            ):
                invocation['artifact'] = artifact
            continue
        if (
            item.get('type') == 'provider_activity'
            and isinstance(invocation_id, str)
            and invocation_id in invocations
        ):
            activity = _nested_provider_activity(item)
            if activity:
                _upsert_provider_activity(invocations[invocation_id], activity)
            continue
        if (
            item.get('type') == 'tool_call'
            and isinstance(parent_id, str)
            and isinstance(invocation_id, str)
            and invocation_id in invocations
        ):
            if (invocation_id, item.get('id')) not in native_activity_ids:
                invocations[invocation_id]['activities'].append({**item, 'legacy': True})
            continue
        if item.get('type') == 'tool_call' and item.get('id') in parent_ids:
            continue
        output.append(item)
    for invocation in invocations.values():
        invocation['activities'].sort(
            key=lambda activity: activity.get('sequence', float('inf')),
        )
    return output


def _nested_provider_activity(item: dict) -> dict | None:
    required = ('activityId', 'sequence', 'kind', 'status', 'title', 'summary')
    if any(key not in item for key in required):
        return None
    activity = {
        'id': item['activityId'],
        'sequence': item['sequence'],
        'kind': item['kind'],
        'status': item['status'],
        'title': item['title'],
        'summary': item['summary'],
        'legacy': False,
    }
    if item.get('files'):
        activity['files'] = item['files']
    return activity


def _nested_provider_artifact(item: dict) -> dict | None:
    required = ('artifactId', 'kind', 'stateRevision', 'thumbnailDataUrl', 'alt')
    if any(key not in item for key in required):
        return None
    return {
        'id': item['artifactId'],
        'kind': item['kind'],
        'stateRevision': item['stateRevision'],
        'thumbnailDataUrl': item['thumbnailDataUrl'],
        'alt': item['alt'],
    }


def _nested_provider_message(item: dict) -> dict | None:
    required = ('messageId', 'role', 'text')
    if any(key not in item for key in required):
        return None
    if item['role'] not in {'user', 'assistant'}:
        return None
    if not isinstance(item['messageId'], str) or not isinstance(item['text'], str):
        return None
    return {'id': item['messageId'], 'role': item['role'], 'text': item['text']}


def _upsert_provider_activity(invocation: dict, activity: dict) -> None:
    for existing in invocation['activities']:
        if existing.get('id') == activity['id']:
            existing.update(activity)
            return
    invocation['activities'].append(activity)


def _upsert_provider_message(invocation: dict, message: dict) -> None:
    messages = invocation.setdefault('messages', [])
    for existing in messages:
        if existing.get('id') == message['id']:
            existing.update(message)
            return
    messages.append(message)
