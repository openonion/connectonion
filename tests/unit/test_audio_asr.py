"""Provider routing with synthetic auth and HTTP, never a real account."""
import importlib
import json
import sys
from pathlib import Path
from types import ModuleType

import httpx
import pytest
import typer
from typer.testing import CliRunner

ROOT = Path(__file__).resolve().parents[2] / 'connectonion'
PREFIX = '_audio_asr_fixture'
for suffix, path in [('', ROOT), ('.cli', ROOT/'cli'), ('.cli.commands', ROOT/'cli/commands')]:
    package = ModuleType(PREFIX + suffix)
    package.__path__ = [str(path)]
    sys.modules[package.__name__] = package


def module():
    return importlib.import_module(PREFIX + '.audio_asr')


@pytest.fixture
def audio(tmp_path, monkeypatch):
    path = tmp_path/'synthetic.m4a'
    path.write_bytes(b'synthetic-audio-container')
    home = tmp_path/'codex'
    home.mkdir()
    (home/'auth.json').write_text(json.dumps({'auth_mode': 'chatgpt', 'tokens': {
        'access_token': 'synthetic-token', 'account_id': 'synthetic-account'}}))
    monkeypatch.setenv('CODEX_HOME', str(home))
    monkeypatch.delenv('ASR_PROVIDER', raising=False)
    monkeypatch.delenv('ASR_MODEL', raising=False)
    return path


def transport(monkeypatch, handler):
    asr = module()
    real_client = httpx.Client
    monkeypatch.setattr(asr, '_http_client', lambda: real_client(
        transport=httpx.MockTransport(handler), follow_redirects=False))


def test_default_and_configured_selection(audio, monkeypatch):
    asr = module()
    assert asr.selected_provider() == 'codex'
    monkeypatch.setenv('ASR_PROVIDER', 'connectonion')
    assert asr.selected_provider() == 'connectonion'
    assert asr.selected_provider('codex') == 'codex'
    monkeypatch.setenv('ASR_PROVIDER', 'typo')
    with pytest.raises(asr.ASRError, match='ASR_PROVIDER'):
        asr.asr(audio)


def test_codex_upload_and_unicode_result(audio, monkeypatch):
    seen = []
    def handler(request):
        seen.append(request)
        assert str(request.url) == 'https://chatgpt.com/backend-api/transcribe'
        assert request.headers['authorization'] == 'Bearer synthetic-token'
        assert request.headers['chatgpt-account-id'] == 'synthetic-account'
        assert b'synthetic-audio-container' in request.content
        assert b'name="language"' in request.content and b'zh' in request.content
        return httpx.Response(200, json={'text': '你好，OpenOnion'})
    transport(monkeypatch, handler)
    assert module().asr(audio, language='zh') == {'provider': 'codex', 'text': '你好，OpenOnion'}
    assert len(seen) == 1


@pytest.mark.parametrize('status', [302, 401, 403, 429, 500])
def test_codex_errors_no_redirect_retry_fallback_or_leak(audio, monkeypatch, status):
    calls = []
    def handler(request):
        calls.append(request)
        return httpx.Response(status, text='sensitive-body-synthetic-token',
                              headers={'location': 'https://example.com/leak'})
    transport(monkeypatch, handler)
    monkeypatch.setattr(module(), '_connectonion', lambda *args: pytest.fail('fallback'))
    with pytest.raises(module().ASRError) as error:
        module().asr(audio)
    assert len(calls) == 1
    assert 'sensitive-body' not in str(error.value) and 'synthetic-token' not in str(error.value)


@pytest.mark.parametrize('payload', [b'not-json', b'[]', b'{"text":42}', b'{}'])
def test_invalid_result_is_not_success(audio, monkeypatch, payload):
    transport(monkeypatch, lambda request: httpx.Response(200, content=payload))
    with pytest.raises(module().ASRError):
        module().asr(audio)


def test_empty_transcript_is_valid_for_silence(audio, monkeypatch):
    transport(monkeypatch, lambda request: httpx.Response(200, json={'text': ''}))
    assert module().asr(audio)['text'] == ''


@pytest.mark.parametrize('auth', [{}, {'auth_mode': 'apikey'}, {'tokens': []},
    {'tokens': {'access_token': 'bad\nheader'}}, {'tokens': {'access_token': 4}}])
def test_auth_failure_stays_local(audio, monkeypatch, auth):
    (Path(__import__('os').environ['CODEX_HOME'])/'auth.json').write_text(json.dumps(auth))
    monkeypatch.setattr(module(), '_http_client', lambda: pytest.fail('network before auth'))
    with pytest.raises(module().ASRError, match='codex login'):
        module().asr(audio)


def test_cloud_provider_only_uses_existing_sdk(audio, monkeypatch):
    calls = []
    fake = ModuleType(PREFIX+'.transcribe')
    fake.transcribe = lambda path, **kwargs: calls.append((path, kwargs)) or 'cloud text'
    sys.modules[fake.__name__] = fake
    monkeypatch.setenv('ASR_PROVIDER', 'connectonion')
    monkeypatch.setenv('ASR_MODEL', 'co/test-fixture')
    monkeypatch.setattr(module(), '_codex', lambda *args: pytest.fail('wrong provider'))
    assert module().asr(audio, language='en')['text'] == 'cloud text'
    assert calls[0][1]['model'] == 'co/test-fixture'
    assert 'en' in calls[0][1]['prompt']
    monkeypatch.setenv('ASR_MODEL', 'gemini-direct')
    with pytest.raises(module().ASRError, match='ASR_MODEL'):
        module().asr(audio)
    assert len(calls) == 1


def test_bad_audio_rejected_before_auth_or_http(audio, monkeypatch, tmp_path):
    monkeypatch.setattr(module(), '_codex', lambda *args: pytest.fail('invalid input'))
    empty = tmp_path/'empty.wav'
    empty.touch()
    for path in [tmp_path/'missing.wav', empty, tmp_path]:
        with pytest.raises(module().ASRError):
            module().asr(path)


@pytest.mark.parametrize('failure', [ValueError('sensitive-body'),
    httpx.ConnectError('sensitive-token'), KeyError('sensitive-body'), IndexError('empty choices'), None, 42])
def test_cloud_failure_is_safe_and_does_not_call_codex(audio, monkeypatch, failure):
    fake = ModuleType(PREFIX+'.transcribe')
    def transcribe(*args, **kwargs):
        if isinstance(failure, Exception):
            raise failure
        return failure
    fake.transcribe = transcribe
    sys.modules[fake.__name__] = fake
    monkeypatch.setenv('ASR_MODEL', 'co/synthetic')
    monkeypatch.setattr(module(), '_codex', lambda *args: pytest.fail('fallback'))
    with pytest.raises(module().ASRError) as error:
        module().asr(audio, provider='connectonion')
    assert 'sensitive' not in str(error.value)


def test_cli_help_json_and_error(audio, monkeypatch):
    commands = importlib.import_module(PREFIX+'.cli.commands.asr_commands')
    app = typer.Typer()
    app.command('asr')(commands.transcribe_audio)
    runner = CliRunner()
    result = runner.invoke(app, ['--help'])
    assert result.exit_code == 0 and '--provider' in result.output and 'Codex' in result.output
    monkeypatch.setattr(module(), 'asr', lambda *args, **kwargs: {'provider': 'codex', 'text': '你好'})
    result = runner.invoke(app, [str(audio), '--json'])
    assert result.exit_code == 0 and json.loads(result.stdout)['text'] == '你好'
    def failed(*args, **kwargs):
        raise module().ASRError('fixture-error. Next: co asr --help')
    monkeypatch.setattr(module(), 'asr', failed)
    result = runner.invoke(app, [str(audio), '--json'])
    assert result.exit_code == 1 and json.loads(result.stdout)['ok'] is False
