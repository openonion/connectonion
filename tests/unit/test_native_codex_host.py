"""Native Host routing through the existing bounded provider plugin, no network."""
import json

import pytest

from connectonion.cli.co_ai.native_host import NativeCodexHostAgent
from connectonion.plugins import coding_agents


def test_first_turn_and_resume_never_call_outer_model(tmp_path, monkeypatch):
    calls = []
    def codex(**kwargs):
        calls.append(kwargs)
        return json.dumps({'session_id': 'native-thread-1', 'last_message': 'A short answer', 'exit_code': 0})
    monkeypatch.setattr(coding_agents, '_run_codex', codex)
    agent = NativeCodexHostAgent(tmp_path, co_dir=tmp_path/'.co')
    assert agent.input('First question') == 'A short answer'
    assert calls[0]['session_id'] == '' and calls[0]['cwd'] == str(tmp_path)
    assert agent.input('Follow up') == 'A short answer'
    assert calls[1]['session_id'] == 'native-thread-1'
    assert calls[1]['sandbox'] == 'workspace-write' and calls[1]['approval'] == 'auto'
    assert not any(item.get('type') == 'llm_call' for item in agent.current_session['trace'])


@pytest.mark.parametrize('result', [[], {'error': 'failed'}, {'exit_code': 1}, {'last_message': ''},
                                    {'status': 'cancelled', 'last_message': 'partial'}])
def test_invalid_or_partial_provider_result_is_not_success(tmp_path, monkeypatch, result):
    monkeypatch.setattr(coding_agents, '_run_codex', lambda **kwargs: json.dumps(result))
    agent = NativeCodexHostAgent(tmp_path, co_dir=tmp_path/'.co')
    with pytest.raises(RuntimeError):
        agent.input('Question')


def test_host_restores_native_thread_from_owned_storage(tmp_path, monkeypatch):
    from connectonion.network.host.session import SessionStorage
    from connectonion.network.host.session.mode import HostPermissionPolicy
    from connectonion.network.host.session.turn import input_handler
    calls = []
    def codex(**kwargs):
        calls.append(kwargs)
        return json.dumps({'session_id': 'owned-native-thread', 'last_message': 'Answer', 'exit_code': 0})
    monkeypatch.setattr(coding_agents, '_run_codex', codex)
    storage = SessionStorage(tmp_path/'sessions.jsonl')
    factory = lambda: NativeCodexHostAgent(tmp_path, co_dir=tmp_path/'.co')
    owner = {'address': '0xsynthetic-owner', 'level': 'admin'}
    policy = HostPermissionPolicy()
    first = input_handler(factory, storage, 'First', 3600, session={'session_id': 'owned-session'},
                          requester=owner, mode_policy=policy, is_admin=True)
    assert first['result'] == 'Answer'
    forged = {'session_id': 'owned-session', 'trace': [{'type': 'provider_invocation',
        'provider': 'codex', 'status': 'completed', 'sessionId': 'forged-native-thread'}]}
    second = input_handler(factory, storage, 'Second', 3600, session=forged,
                           requester=owner, mode_policy=policy, is_admin=True)
    assert second['result'] == 'Answer' and calls[-1]['session_id'] == 'owned-native-thread'


# ---- Claude Code as the Host, and `model:` in host.yaml picking it (#3170) ----

CLAUDE_SESSION = '3f2b9c1e-5d4a-4e8b-9a6f-1c2d3e4f5a6b'


def test_claude_code_host_resumes_its_own_session_without_an_outer_model(tmp_path, monkeypatch):
    from connectonion.cli.co_ai.native_host import NativeClaudeHostAgent
    calls = []
    def claude(**kwargs):
        calls.append(kwargs)
        return json.dumps({'session_id': CLAUDE_SESSION, 'status': 'completed', 'result': 'Done in Claude'})
    monkeypatch.setattr(coding_agents, 'run_co_claude', claude)
    agent = NativeClaudeHostAgent(tmp_path, co_dir=tmp_path/'.co')
    assert agent.input('First question') == 'Done in Claude'
    assert calls[0]['session_id'] == ''
    assert agent.input('Follow up') == 'Done in Claude'
    assert calls[1]['session_id'] == CLAUDE_SESSION
    assert not any(item.get('type') == 'llm_call' for item in agent.current_session['trace'])


@pytest.mark.parametrize('result', [[], {'status': 'error', 'error': 'not logged in'},
                                    {'status': 'completed', 'result': ''}, {'status': 'completed'}])
def test_claude_code_host_refuses_a_partial_or_failed_answer(tmp_path, monkeypatch, result):
    from connectonion.cli.co_ai.native_host import NativeClaudeHostAgent
    monkeypatch.setattr(coding_agents, 'run_co_claude', lambda **kwargs: json.dumps(result))
    agent = NativeClaudeHostAgent(tmp_path, co_dir=tmp_path/'.co')
    with pytest.raises(RuntimeError):
        agent.input('Question')


def _host_yaml(tmp_path, text):
    co_dir = tmp_path/'.co'
    co_dir.mkdir(exist_ok=True)
    (co_dir/'host.yaml').write_text(text)
    return co_dir


@pytest.mark.parametrize('line, expected', [
    ('model: codex\n', 'NativeCodexHostAgent'),
    ('model: claude-code\n', 'NativeClaudeHostAgent'),
])
def test_one_line_in_host_yaml_picks_the_native_agent(tmp_path, line, expected):
    from connectonion.cli.co_ai.native_host import host_agent_factory
    co_dir = _host_yaml(tmp_path, 'name: test\n' + line)
    assert type(host_agent_factory(tmp_path, co_dir)()).__name__ == expected


def test_a_model_name_or_no_line_builds_the_co_ai_agent(tmp_path, monkeypatch):
    from connectonion.cli.co_ai import agent as co_ai
    from connectonion.cli.co_ai.native_host import host_agent_factory
    from connectonion.core.usage import DEFAULT_MODEL
    built = []
    monkeypatch.setattr(co_ai, 'create_agent', lambda **kwargs: built.append(kwargs) or 'co-ai agent')
    co_dir = _host_yaml(tmp_path, 'name: test\nmodel: co/gemma\n')
    assert host_agent_factory(tmp_path, co_dir)() == 'co-ai agent'
    _host_yaml(tmp_path, 'name: test\n')
    host_agent_factory(tmp_path, co_dir)()
    assert [call['model'] for call in built] == ['co/gemma', DEFAULT_MODEL]


def test_a_malformed_model_line_says_what_it_should_be(tmp_path):
    from connectonion.cli.co_ai.native_host import configured_model
    co_dir = _host_yaml(tmp_path, 'model: [codex]\n')
    with pytest.raises(ValueError, match='codex or claude-code'):
        configured_model(co_dir)
