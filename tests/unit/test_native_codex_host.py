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
    assert calls[1]['sandbox'] == 'workspace-write' and calls[1]['approval'] == 'manual'
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
