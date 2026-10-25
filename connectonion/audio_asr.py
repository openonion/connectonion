"""Provider-selectable ASR. No auth reads, uploads or model calls on import.

Codex's unofficial desktop dictation protocol was investigated with Wangnov's
MIT-licensed codex-asr project; see docs/asr.md for attribution and limitations.
This is a Python implementation, with no Rust CLI or local server dependency.
"""
from __future__ import annotations

import base64
import json
import os
from pathlib import Path
import re
from typing import Callable

import httpx

CODEX_ENDPOINT = 'https://chatgpt.com/backend-api/transcribe'
MAX_AUDIO_BYTES = 50 * 1024 * 1024
MAX_RESPONSE_BYTES = 1024 * 1024
MIME_TYPES = {'.wav': 'audio/wav', '.mp3': 'audio/mpeg', '.m4a': 'audio/mp4',
              '.mp4': 'audio/mp4', '.flac': 'audio/flac', '.ogg': 'audio/ogg',
              '.webm': 'audio/webm'}


class ASRError(ValueError):
    """A safe user-facing failure; never contains credentials or response bodies."""


class ASRInterrupted(ASRError):
    """A resumable long recording with separately retained raw segment results."""
    def __init__(self, identifier, completed, *, cancelled=False, reason=None):
        from .asr_jobs import merge
        self.job_id = identifier
        self.completed_segments = len(completed)
        self.partial_text = merge(completed)
        self.exit_code = 130 if cancelled else 1
        super().__init__(f'ASR {"cancelled" if cancelled else "interrupted"}; {len(completed)} parts saved locally. '
                         f'{reason or ""} '
                         f'Next: co asr <same-audio-file> --resume {identifier}')


def selected_provider(provider: str | None = None) -> str:
    """Explicit choice overrides ASR_PROVIDER; otherwise use Codex."""
    value = provider if provider is not None else os.environ.get('ASR_PROVIDER', 'codex')
    if value not in ('codex', 'connectonion'):
        raise ASRError('Unknown ASR_PROVIDER. Next: co env set ASR_PROVIDER codex')
    return value


def request_provider(provider: str | None = None, resume: str | None = None) -> str:
    if not resume:
        return selected_provider(provider)
    from .asr_jobs import load
    saved = load(resume)['provider']
    if provider is not None and selected_provider(provider) != saved:
        raise ASRError('A resumed job must keep its original provider. Next: co asr --help')
    return saved


def asr(audio: str | Path, *, provider: str | None = None,
        language: str | None = None, resume: str | None = None,
        progress: Callable[[int, int], None] | None = None) -> dict:
    """Upload a selected audio file to one provider and return provider/text.

    Codex is the default cloud provider, not local recognition. File-backed
    Codex ChatGPT login is required. There is no automatic retry or fallback.
    ConnectOnion reuses transcribe(), with existing co credentials and pricing.
    Long recordings use private per-part checkpoints and can resume with the
    returned job ID. The caller decides whether results enter memory.
    """
    chosen = request_provider(provider, resume)
    path = Path(audio).expanduser().resolve()
    _validate_audio(path)
    if language is not None and not re.fullmatch(r'[A-Za-z]{2,3}(?:-[A-Za-z0-9]{2,8})*', language):
        raise ASRError('Invalid language hint. Next: co asr --help')
    from .asr_media import probe_duration, WINDOW_SECONDS
    duration = probe_duration(path)
    if resume or duration > WINDOW_SECONDS or path.stat().st_size > MAX_AUDIO_BYTES or path.suffix.lower() not in MIME_TYPES:
        from .asr_jobs import load, run
        if resume:
            saved = load(resume)
            if language is not None and language != saved['language']:
                raise ASRError('Resume must keep the recorded language. Next: co asr --help')
            language, model = saved['language'], saved['model']
        else:
            model = _cloud_model() if chosen == 'connectonion' else None
        operation = (lambda clip: _codex(clip, language)) if chosen == 'codex' else (
            lambda clip: _connectonion(clip, language, model))
        return run(path, duration, chosen, language, model, operation, resume=resume, progress=progress)
    text = _codex(path, language) if chosen == 'codex' else _connectonion(path, language)
    return {'provider': chosen, 'text': text}


def _validate_audio(path: Path) -> None:
    try:
        valid = path.is_file() and path.stat().st_size > 0
    except OSError:
        valid = False
    if not valid:
        raise ASRError('Audio must be a readable, nonempty file. Next: co asr --help')


def _header_value(value: object) -> bool:
    return isinstance(value, str) and bool(value) and all(33 <= ord(c) <= 126 for c in value)


def _codex_headers() -> dict[str, str]:
    home = Path(os.environ.get('CODEX_HOME') or Path.home()/'.codex').expanduser()
    try:
        with (home/'auth.json').open('rb') as stream:
            raw = stream.read(MAX_RESPONSE_BYTES + 1)
        if len(raw) > MAX_RESPONSE_BYTES:
            raise ValueError('oversized auth')
        auth = json.loads(raw)
        mode = auth.get('auth_mode', auth.get('authMode'))
        tokens = auth.get('tokens')
        token = tokens.get('access_token') if isinstance(tokens, dict) else None
        if mode not in (None, 'chatgpt', 'chatgpt_auth_tokens') or not _header_value(token):
            raise ValueError('unsupported auth')
        account = tokens.get('account_id') or _jwt_account(token)
        if account is not None and not _header_value(account):
            raise ValueError('invalid account')
    except (OSError, ValueError, AttributeError, TypeError):
        raise ASRError('Codex file-backed ChatGPT login is unavailable. Next: codex login') from None
    headers = {'Authorization': f'Bearer {token}', 'originator': 'Codex Desktop',
               'User-Agent': 'ConnectOnion-ASR (Codex Desktop dictation adapter)'}
    if account:
        headers['ChatGPT-Account-Id'] = account
    return headers


def _jwt_account(token: str) -> str | None:
    """Read only an optional routing claim, never treat a decoded JWT as verified."""
    try:
        payload = token.split('.')[1]
        data = json.loads(base64.urlsafe_b64decode(payload + '=' * (-len(payload) % 4)))
        return data['https://api.openai.com/auth']['chatgpt_account_id']
    except (IndexError, KeyError, ValueError, TypeError):
        return None


def _http_client() -> httpx.Client:
    return httpx.Client(timeout=httpx.Timeout(300, connect=15), follow_redirects=False)


def _codex(path: Path, language: str | None) -> str:
    headers = _codex_headers()
    try:
        with path.open('rb') as audio, _http_client() as client:
            with client.stream('POST', CODEX_ENDPOINT, headers=headers,
                               files={'file': (path.name, audio, MIME_TYPES[path.suffix.lower()])},
                               data={'language': language} if language else {}) as response:
                if response.status_code != 200:
                    action = 'codex login' if response.status_code in (401, 403) else 'co asr --help'
                    raise ASRError(f'Codex ASR HTTP {response.status_code}; no fallback. Next: {action}')
                body = bytearray()
                for chunk in response.iter_bytes():
                    body.extend(chunk)
                    if len(body) > MAX_RESPONSE_BYTES:
                        raise ASRError('Codex ASR response too large. Next: co asr --help')
        result = json.loads(body)
        if not isinstance(result, dict) or not isinstance(result.get('text'), str):
            raise ValueError('missing transcript')
        return result['text']
    except (httpx.HTTPError, OSError):
        raise ASRError('Codex ASR request failed; no automatic retry or fallback. Next: co asr --help') from None
    except (ValueError, UnicodeError) as error:
        if isinstance(error, ASRError):
            raise
        raise ASRError('Codex ASR returned an invalid transcript. Next: co asr --help') from None


def _cloud_model() -> str:
    model = os.environ.get('ASR_MODEL')
    if model is None:
        from .core.usage import DEFAULT_MODEL
        model = DEFAULT_MODEL
    if not model.startswith('co/'):
        raise ASRError('ASR_MODEL must select a co/ model. Next: co env unset ASR_MODEL')
    return model


def _connectonion(path: Path, language: str | None, model: str | None = None) -> str:
    from .transcribe import transcribe
    model = model or _cloud_model()
    prompt = f'Transcribe the audio verbatim. Language hint: {language}.' if language else None
    # Provider errors may contain upstream bodies: keep that text out of CLI/logs.
    try:
        text = transcribe(str(path), model=model, prompt=prompt)
    except (httpx.HTTPError, OSError, ValueError, KeyError, IndexError, TypeError, AttributeError):
        raise ASRError('ConnectOnion ASR failed; check authentication, credits and model. Next: co auth status') from None
    if not isinstance(text, str):
        raise ASRError('ConnectOnion ASR returned an invalid transcript. Next: co asr --help')
    return text
