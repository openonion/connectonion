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
    monkeypatch.setenv('AGENT_CONFIG_PATH', str(tmp_path/'co'))
    media = importlib.import_module(PREFIX+'.asr_media')
    monkeypatch.setattr(media, 'probe_duration', lambda path: 5.0)
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
    from rich.text import Text
    help_text = Text.from_ansi(result.output).plain
    assert result.exit_code == 0 and '--provider' in help_text and 'Codex' in help_text
    monkeypatch.setattr(module(), 'asr', lambda *args, **kwargs: {'provider': 'codex', 'text': '你好'})
    result = runner.invoke(app, [str(audio), '--json'])
    assert result.exit_code == 0 and json.loads(result.stdout)['text'] == '你好'
    def failed(*args, **kwargs):
        raise module().ASRError('fixture-error. Next: co asr --help')
    monkeypatch.setattr(module(), 'asr', failed)
    result = runner.invoke(app, [str(audio), '--json'])
    assert result.exit_code == 1 and json.loads(result.stdout)['ok'] is False


@pytest.fixture
def long_audio(audio, monkeypatch):
    media = importlib.import_module(PREFIX+'.asr_media')
    jobs = importlib.import_module(PREFIX+'.asr_jobs')
    monkeypatch.setattr(media, 'probe_duration', lambda path: 1000.0)
    exported = []
    def export(source, target, start, end):
        exported.append((start, end))
        target.write_bytes(b'synthetic-converted-audio')
    monkeypatch.setattr(jobs, 'export_window', export)
    return audio, exported, jobs


def test_three_hour_planning_and_no_input_size_limit(audio):
    media = importlib.import_module(PREFIX+'.asr_media')
    planned = media.windows(10800.0)
    assert len(planned) == 23 and planned[0] == (0, 482) and planned[-1] == (10560, 10800)
    with audio.open('r+b') as file:
        file.truncate(60 * 1024 * 1024)
    module()._validate_audio(audio)


def test_long_recording_checkpoint_and_merge(long_audio, monkeypatch):
    audio, exported, jobs = long_audio
    texts = iter(['We discussed the OpenOnion project', 'the OpenOnion project is green', 'Next steps are ready'])
    monkeypatch.setattr(module(), '_codex', lambda *args: next(texts))
    progress = []
    result = module().asr(audio, progress=lambda part, total: progress.append((part, total)))
    assert exported == [(0, 482), (480, 962), (960, 1000)]
    assert len(result['segments']) == 3 and progress == [(1, 3), (2, 3), (3, 3)]
    assert result['text'].count('OpenOnion project') == 2
    assert result['boundary_overlap_seconds'] == 2.0
    state = jobs.load(result['job_id'])
    assert state['completed'][1]['text'] == 'the OpenOnion project is green'
    directory = jobs._directory(result['job_id'])
    assert directory.stat().st_mode & 0o777 == 0o700
    assert (directory/'state.json').stat().st_mode & 0o777 == 0o600
    assert not list(directory.glob('segment-*'))


def test_resume_only_unfinished_parts_and_freezes_provider(long_audio, monkeypatch):
    audio, exported, jobs = long_audio
    calls = []
    def interrupted(path, language):
        calls.append(path)
        if len(calls) == 2:
            raise module().ASRError('upstream failed')
        return 'first part'
    monkeypatch.setattr(module(), '_codex', interrupted)
    with pytest.raises(module().ASRInterrupted) as error:
        module().asr(audio, language='en')
    failure = error.value
    assert failure.completed_segments == 1 and failure.partial_text == 'first part'
    assert len(jobs.load(failure.job_id)['completed']) == 1
    monkeypatch.setenv('ASR_PROVIDER', 'connectonion')
    monkeypatch.setenv('ASR_MODEL', 'invalid-changed-config')
    with pytest.raises(module().ASRError):
        module().asr(audio, provider='connectonion', resume=failure.job_id)
    monkeypatch.setattr(module(), '_codex', lambda *args: 'remaining')
    result = module().asr(audio, resume=failure.job_id)
    assert result['provider'] == 'codex' and len(result['segments']) == 3
    assert exported == [(0, 482), (480, 962), (480, 962), (960, 1000)]
    monkeypatch.setattr(module(), '_codex', lambda *args: pytest.fail('completed job re-uploaded'))
    assert module().asr(audio, resume=failure.job_id)['text'] == result['text']


def test_resume_rejects_changed_original_and_corrupt_checkpoint(long_audio, monkeypatch):
    audio, _, jobs = long_audio
    monkeypatch.setattr(module(), '_codex', lambda *args: 'done')
    result = module().asr(audio)
    audio.write_bytes(b'changed-original')
    with pytest.raises(module().ASRError, match='Audio changed'):
        module().asr(audio, resume=result['job_id'])
    state_path = jobs._directory(result['job_id'])/'state.json'
    state = json.loads(state_path.read_text())
    state['completed'][0]['text'] = {'bad': 'type'}
    state_path.write_text(json.dumps(state))
    with pytest.raises(module().ASRError, match='checkpoint'):
        module().asr(audio, resume=result['job_id'])


def test_checkpoint_write_failure_does_not_claim_unsaved_result(long_audio, monkeypatch):
    audio, _, jobs = long_audio
    monkeypatch.setattr(module(), '_codex', lambda *args: 'not-persisted')
    original = jobs._save
    def save(directory, state):
        if state['completed']:
            raise OSError('disk full')
        original(directory, state)
    monkeypatch.setattr(jobs, '_save', save)
    with pytest.raises(module().ASRInterrupted) as error:
        module().asr(audio)
    assert error.value.completed_segments == 0
    assert jobs.load(error.value.job_id)['completed'] == []


def test_same_job_cannot_run_twice(long_audio, monkeypatch):
    audio, _, jobs = long_audio
    monkeypatch.setattr(module(), '_codex', lambda *args: 'done')
    result = module().asr(audio)
    directory = jobs._directory(result['job_id'])
    before = (directory/'state.json').read_bytes()
    with jobs._lock(directory):
        with pytest.raises(module().ASRError, match='already running'):
            module().asr(audio, resume=result['job_id'])
    assert (directory/'state.json').read_bytes() == before


def test_repeated_speech_is_not_silently_deleted(long_audio):
    _, _, jobs = long_audio
    phrase = 'Thank you everyone for coming today'
    assert jobs.merge([{'text': phrase}, {'text': phrase + ' Let us begin.'}]).count(phrase) == 2


def test_resume_rejects_shortened_checkpoint_plan(long_audio, monkeypatch):
    audio, _, jobs = long_audio
    monkeypatch.setattr(module(), '_codex', lambda *args: 'done')
    result = module().asr(audio)
    path = jobs._directory(result['job_id'])/'state.json'
    state = json.loads(path.read_text())
    state.update(duration=1.0, segments=[[0.0, 1.0]], completed=[{'start': 0.0, 'end': 1.0, 'text': 'shortened'}])
    assert jobs._valid(state)
    path.write_text(json.dumps(state))
    monkeypatch.setattr(module(), '_codex', lambda *args: pytest.fail('invalid plan uploaded'))
    with pytest.raises(module().ASRError, match='duration differs'):
        module().asr(audio, resume=result['job_id'])


def test_cancel_keeps_completed_work(long_audio, monkeypatch):
    audio, _, jobs = long_audio
    count = []
    def interrupted(*args):
        count.append(1)
        if len(count) == 2:
            raise KeyboardInterrupt
        return 'saved before cancellation'
    monkeypatch.setattr(module(), '_codex', interrupted)
    with pytest.raises(module().ASRInterrupted) as error:
        module().asr(audio)
    assert error.value.exit_code == 130 and error.value.completed_segments == 1
    assert len(jobs.load(error.value.job_id)['completed']) == 1


def test_real_local_audio_inspection_and_split(tmp_path, monkeypatch):
    import shutil
    import subprocess
    import wave
    ffmpeg = shutil.which('ffmpeg')
    if not ffmpeg or not shutil.which('ffprobe'):
        pytest.skip('FFmpeg is not installed in this test environment')
    media = importlib.import_module(PREFIX+'.asr_media')
    source = tmp_path/'ten-minute-silence.m4a'
    subprocess.run([ffmpeg, '-nostdin', '-v', 'error', '-f', 'lavfi', '-i',
                    'anullsrc=r=16000:cl=mono', '-t', '601', '-c:a', 'aac', str(source)],
                   check=True, timeout=30)
    duration = media.probe_duration(source)
    assert 600.9 <= duration <= 601.1
    target = tmp_path/'first-window.wav'
    media.export_window(source, target, *media.windows(duration)[0])
    with wave.open(str(target)) as wave_file:
        assert wave_file.getnchannels() == 1 and wave_file.getframerate() == 16000
        assert abs(wave_file.getnframes()/16000 - 482) < .1
    assert target.stat().st_size < module().MAX_AUDIO_BYTES
