import json
from datetime import datetime, timezone

from connectonion.rem.files import state_path, write_json
from connectonion.rem.skill_usage import VERSION, session_samples


def test_session_sample_keeps_request_failure_and_final_reply_but_not_next_task(tmp_path):
    when = datetime.now(timezone.utc).isoformat()
    path = tmp_path / 'session.jsonl'
    def message(role, text, stamp=when):
        return {'type': 'response_item', 'timestamp': stamp,
                'payload': {'type': 'message', 'role': role, 'content': [{'type': 'input_text', 'text': text}]}}
    rows = [
        {'type': 'session_meta', 'payload': {'id': 'session', 'cwd': '/work'}},
        message('user', 'Review the docs', '2000-01-01T00:00:00Z'),
        {'type': 'response_item', 'timestamp': when,
         'payload': {'type': 'function_call', 'name': 'exec', 'arguments': 'cat /skills/example/SKILL.md'}},
        {'type': 'response_item', 'timestamp': when,
         'payload': {'type': 'function_call_output', 'output': 'exit 1: missing source directory'}},
        message('assistant', 'Blocked: no output artifact was produced.'),
        message('user', 'Unrelated private task'),
    ]
    path.write_text('\n'.join(json.dumps(row) for row in rows))
    write_json(state_path(tmp_path, 'skill-usage.json'), {'version': VERSION, 'files': {
        str(path): {'events': [['example', when, 'codex', '/work']]},
        '/missing-own-run.jsonl': {'events': [['example', when, 'codex', str(tmp_path / '.state/tasks')]]},
        '/missing-unrelated.jsonl': {'events': [['other', when, 'codex', '/work']]},
    }})
    result = session_samples(tmp_path, 'example')
    assert result['matched_invocations'] == 1 and not result['missing']
    assert len(result['items']) == 1
    text = result['items'][0]['text']
    assert 'Review the docs' in text and 'missing source directory' in text
    assert 'no output artifact' in text and 'Unrelated private task' not in text
    assert result['items'][0]['reference'] == path.as_uri()


def test_claude_sample_includes_tool_results_and_stops_at_end_turn(tmp_path):
    when = datetime.now(timezone.utc).isoformat()
    path = tmp_path / 'claude.jsonl'
    rows = [
        {'type': 'assistant', 'timestamp': when, 'message': {'role': 'assistant', 'content': [
            {'type': 'tool_use', 'name': 'Skill', 'input': {'skill': 'plugin:example'}}]}},
        {'type': 'user', 'timestamp': when, 'message': {'role': 'user', 'content': [
            {'type': 'tool_result', 'content': 'Permission denied: artifact not written'}]}},
        {'type': 'assistant', 'timestamp': when, 'message': {'role': 'assistant', 'stop_reason': 'end_turn',
                                                         'content': [{'type': 'text', 'text': 'Failed to write'}]}},
        {'type': 'assistant', 'timestamp': when, 'message': {'role': 'assistant', 'content': [
            {'type': 'text', 'text': 'Later unrelated output'}]}},
    ]
    path.write_text('\n'.join(json.dumps(row) for row in rows))
    write_json(state_path(tmp_path, 'skill-usage.json'), {'version': VERSION, 'files': {
        str(path): {'events': [['plugin:example', when, 'claude-code', '/work']]}}})
    text = session_samples(tmp_path, 'example')['items'][0]['text']
    assert 'Permission denied' in text and 'Failed to write' in text
    assert 'Later unrelated output' not in text


def test_missing_session_and_sampling_limit_are_explicit(tmp_path):
    when = datetime.now(timezone.utc).isoformat()
    write_json(state_path(tmp_path, 'skill-usage.json'), {'version': VERSION, 'files': {
        '/missing-a.jsonl': {'events': [['example', when, 'codex', '/work']]},
        '/missing-b.jsonl': {'events': [['example', when, 'codex', '/work']]}}})
    result = session_samples(tmp_path, 'example', limit=1)
    assert result['matched_invocations'] == 2 and result['sample_limit'] == 1
    assert len(result['missing']) == 1 and not result['items']
