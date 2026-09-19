"""Public local-provider behavior through the real SDK with an HTTP transport."""
import json

import httpx
import openai
import pytest
from pydantic import BaseModel, ValidationError

from connectonion import Agent, llm_do
from connectonion.core.llm import create_llm, LLMConnectionError


class Note(BaseModel):
    completed: list[str]
    pending: list[str]


@pytest.fixture
def endpoint(monkeypatch):
    calls, replies = [], []
    real_client = openai.OpenAI

    def send(request):
        calls.append((request, json.loads(request.content)))
        reply = replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        status, payload = reply if isinstance(reply, tuple) else (200, reply)
        return httpx.Response(status, json=payload)

    def client(**kwargs):
        return real_client(**kwargs, http_client=httpx.Client(transport=httpx.MockTransport(send)))

    monkeypatch.setattr(openai, 'OpenAI', client)
    monkeypatch.delenv('OLLAMA_BASE_URL', raising=False)
    return calls, replies


def response(content='Done', tool_calls=None, finish='stop', usage=True):
    result = {'id': 'local-1', 'object': 'chat.completion', 'created': 0,
              'model': 'local', 'choices': [{'index': 0, 'finish_reason': finish,
              'message': {'role': 'assistant', 'content': content, 'tool_calls': tool_calls}}]}
    if usage:
        result['usage'] = {'prompt_tokens': 30, 'completion_tokens': 5, 'total_tokens': 35}
    return result


def test_local_summary_uses_no_cloud_key_and_preserves_tag(endpoint, monkeypatch):
    calls, replies = endpoint
    monkeypatch.setenv('OPENAI_API_KEY', 'cloud-secret-must-not-leak')
    replies.append(response('今天修复了日志'))
    assert llm_do('总结今天', model='ollama/team/model:q4') == '今天修复了日志'
    req, body = calls[0]
    assert str(req.url) == 'http://localhost:11434/v1/chat/completions'
    assert req.headers['authorization'] == 'Bearer ollama'
    assert body['model'] == 'team/model:q4'
    assert 'tools' not in body


def test_custom_endpoint_reaches_initialization(endpoint, monkeypatch):
    calls, replies = endpoint
    monkeypatch.setenv('OLLAMA_BASE_URL', 'http://wrong.invalid:11434')
    replies.append(response())
    llm_do('hello', model='ollama/local', base_url='http://localhost:1234/', api_key='explicit', max_tokens=12)
    req, body = calls[0]
    assert str(req.url) == 'http://localhost:1234/v1/chat/completions'
    assert req.headers['authorization'] == 'Bearer explicit'
    assert body['max_tokens'] == 12
    assert 'base_url' not in body


def test_ollama_environment_endpoint(endpoint, monkeypatch):
    calls, replies = endpoint
    monkeypatch.setenv('OLLAMA_BASE_URL', 'http://localhost:2222/v1/')
    replies.append(response())
    llm_do('hello', model='ollama/local')
    assert str(calls[0][0].url) == 'http://localhost:2222/v1/chat/completions'


def test_arbitrary_model_with_explicit_endpoint(endpoint, monkeypatch):
    calls, replies = endpoint
    monkeypatch.setenv('OPENAI_API_KEY', 'cloud-secret')
    replies.append(response())
    llm_do('hello', model='my-org/model:tag', base_url='http://localhost:1234/custom/v1')
    req, body = calls[0]
    assert str(req.url) == 'http://localhost:1234/custom/v1/chat/completions'
    assert req.headers['authorization'] == 'Bearer not-required'
    assert body['model'] == 'my-org/model:tag'


def test_structured_summary_uses_schema_and_validates(endpoint):
    calls, replies = endpoint
    replies.append(response('{"completed":["tests passed"],"pending":["deploy"]}'))
    note = llm_do('logs', model='ollama/local', output=Note)
    assert note.pending == ['deploy']
    assert calls[0][1]['response_format']['json_schema']['schema'] == Note.model_json_schema()
    assert json.dumps(Note.model_json_schema()) in calls[0][1]['messages'][0]['content']


@pytest.mark.parametrize('content,finish,error', [
    ('{"completed":[],"pending":[]}', 'length', ValueError),
    ('{"completed":[]}', 'stop', ValidationError),
    ('not JSON', 'stop', ValidationError),
])
def test_bad_structured_result_is_not_a_success(endpoint, content, finish, error):
    _, replies = endpoint
    replies.append(response(content, finish=finish))
    with pytest.raises(error):
        llm_do('logs', model='ollama/local', output=Note)


def test_agent_executes_tool_and_returns_result(endpoint, tmp_path):
    calls, replies = endpoint
    executed = []

    def add(a: int, b: int) -> int:
        """Add two integers."""
        executed.append((a, b))
        return a + b

    replies.extend([response(None, [{'id': 'call_1', 'type': 'function', 'function': {
        'name': 'add', 'arguments': '{"a":2,"b":3}'}}], 'tool_calls'), response('5')])
    agent = Agent('local', model='ollama/local', base_url='http://localhost:11434',
                  tools=[add], quiet=True, log=False, co_dir=tmp_path)
    assert agent.input('Add 2 and 3') == '5'
    assert executed == [(2, 3)]
    assert calls[0][1]['tools'][0]['function']['name'] == 'add'
    assert any(m.get('tool_call_id') == 'call_1' for m in calls[1][1]['messages'])
    assert agent.total_cost == 0


def test_usage_is_not_priced_as_a_cloud_model(endpoint):
    _, replies = endpoint
    replies.append(response())
    result = create_llm('ollama/gpt-5').complete([{'role': 'user', 'content': 'hi'}])
    assert result.usage.input_tokens == 30
    assert result.usage.cost == 0


def test_missing_usage_supported(endpoint):
    _, replies = endpoint
    replies.append(response(usage=False))
    result = create_llm('ollama/local').complete([{'role': 'user', 'content': 'hi'}])
    assert result.content == 'Done'
    assert result.usage is None


@pytest.mark.parametrize('status,message', [(404, 'model local not found'),
    (400, 'model does not support tools'), (400, 'context length exceeded')])
def test_runtime_errors_are_not_swallowed(endpoint, status, message):
    _, replies = endpoint
    replies.append((status, {'error': {'message': message, 'type': 'invalid_request_error'}}))
    with pytest.raises(openai.APIStatusError, match=message):
        llm_do('hello', model='ollama/local')


def test_timeout_has_endpoint_and_cause(endpoint):
    _, replies = endpoint
    replies.extend([httpx.ReadTimeout('stalled')] * 3)
    with pytest.raises(LLMConnectionError) as error:
        llm_do('hello', model='ollama/local')
    assert 'localhost:11434' in str(error.value)
    assert error.value.__cause__ is not None


def test_invalid_endpoint_fails_before_request():
    with pytest.raises(ValueError, match='base_url'):
        create_llm('local', base_url='not-a-url')


def test_empty_ollama_model_rejected():
    with pytest.raises(ValueError, match='model'):
        create_llm('ollama/')


def test_explicit_endpoint_does_not_route_gpt_name_to_cloud(endpoint):
    calls, replies = endpoint
    replies.append(response())
    llm_do('hi', model='gpt-local', base_url='http://localhost:1234')
    assert calls[0][0].url.host == 'localhost'


def test_managed_prefix_cannot_override_endpoint():
    with pytest.raises(ValueError, match='co/'):
        create_llm('co/gpt-5', base_url='http://localhost:1234')


def test_injected_llm_cannot_silently_ignore_endpoint():
    with pytest.raises(ValueError, match='base_url'):
        Agent('local', llm=object(), base_url='http://localhost:1234', log=False)


@pytest.mark.parametrize('payload,expected', [
    (response(None), 'neither text'),
    ({'id': 'x', 'object': 'chat.completion', 'created': 0, 'model': 'x', 'choices': []}, 'no completion'),
])
def test_empty_completion_is_an_error(endpoint, payload, expected):
    _, replies = endpoint
    replies.append(payload)
    with pytest.raises(ValueError, match=expected):
        llm_do('hello', model='ollama/local')


@pytest.mark.parametrize('arguments', ['[]', 'not-json'])
def test_malformed_tool_arguments_do_not_execute(endpoint, arguments, tmp_path):
    _, replies = endpoint
    replies.append(response(None, [{'id': 'call_1', 'type': 'function', 'function': {
        'name': 'action', 'arguments': arguments}}], 'tool_calls'))
    calls = []

    def action() -> str:
        """Record invocation."""
        calls.append(True)
        return 'done'

    agent = Agent('local', model='ollama/local', tools=[action], quiet=True,
                  log=False, co_dir=tmp_path)
    with pytest.raises(ValueError):
        agent.input('do it')
    assert calls == []


def test_generated_tool_id_is_echoed_back(endpoint, tmp_path):
    calls, replies = endpoint

    def action() -> str:
        """Return a value."""
        return 'ok'

    replies.extend([response(None, [{'id': '', 'type': 'function', 'function': {
        'name': 'action', 'arguments': '{}'}}], 'tool_calls'), response('ok')])
    agent = Agent('local', model='ollama/local', tools=[action], quiet=True,
                  log=False, co_dir=tmp_path)
    assert agent.input('do it') == 'ok'
    messages = calls[1][1]['messages']
    assistant = next(m for m in messages if m.get('tool_calls'))
    result = next(m for m in messages if m.get('role') == 'tool')
    assert assistant['tool_calls'][0]['id'] == result['tool_call_id']
    assert result['tool_call_id']
