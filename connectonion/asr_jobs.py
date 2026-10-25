"""Checkpoint long ASR one completed segment at a time, preserving raw text."""
import hashlib
import json
import math
import os
from pathlib import Path
import re
import tempfile
from contextlib import contextmanager
from uuid import UUID, uuid4

from .audio_asr import ASRError, ASRInterrupted, MAX_AUDIO_BYTES
from .asr_media import export_window, windows


def _root() -> Path:
    from .environment import global_config_dir
    return global_config_dir()/'asr'/'jobs'


def _directory(identifier: str) -> Path:
    try:
        if str(UUID(identifier)) != identifier:
            raise ValueError('noncanonical id')
    except (ValueError, AttributeError):
        raise ASRError('Invalid ASR job ID; use the ID from the failed request. Next: co asr --help') from None
    return _root()/identifier


def load(identifier: str) -> dict:
    try:
        state = json.loads((_directory(identifier)/'state.json').read_text())
        if not _valid(state):
            raise ValueError('invalid state')
        return state
    except (OSError, ValueError, KeyError, TypeError):
        raise ASRError('Cannot read this ASR checkpoint; original audio is unchanged. Next: co asr --help') from None


def _valid(state) -> bool:
    required = {'version', 'sha256', 'provider', 'language', 'model', 'duration', 'segments', 'completed'}
    if (not isinstance(state, dict) or not required.issubset(state) or type(state.get('version')) is not int or state['version'] != 1
            or state.get('provider') not in ('codex', 'connectonion')
            or not isinstance(state.get('sha256'), str) or not re.fullmatch('[a-f0-9]{64}', state['sha256'])):
        return False
    duration = state.get('duration')
    segments, completed = state.get('segments'), state.get('completed')
    if (type(duration) not in (int, float) or not math.isfinite(duration) or duration <= 0
            or not isinstance(segments, list) or not isinstance(completed, list)
            or len(segments) != math.ceil(duration / 480) or len(completed) > len(segments)):
        return False
    if state.get('language') is not None and (not isinstance(state['language'], str)
            or not re.fullmatch(r'[A-Za-z]{2,3}(?:-[A-Za-z0-9]{2,8})*', state['language'])):
        return False
    model = state.get('model')
    if (state['provider'] == 'codex' and model is not None) or (state['provider'] == 'connectonion'
            and (not isinstance(model, str) or not model.startswith('co/'))):
        return False
    for index, segment in enumerate(segments):
        if (not isinstance(segment, list) or len(segment) != 2
                or any(type(number) not in (int, float) for number in segment)
                or segment != [index * 480, min(duration, index * 480 + 482)]):
            return False
    return all(isinstance(item, dict) and isinstance(item.get('text'), str)
               and [item.get('start'), item.get('end')] == segments[index]
               for index, item in enumerate(completed))


def _save(directory: Path, state: dict) -> None:
    with tempfile.NamedTemporaryFile(mode='w', dir=directory, delete=False, encoding='utf-8') as file:
        temporary = Path(file.name)
        try:
            os.chmod(temporary, 0o600)
            json.dump(state, file, ensure_ascii=False)
            file.flush()
            os.fsync(file.fileno())
            os.replace(temporary, directory/'state.json')
        finally:
            temporary.unlink(missing_ok=True)


def _digest(path: Path) -> tuple[str, tuple]:
    before = path.stat()
    value = hashlib.sha256()
    with path.open('rb') as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b''):
            value.update(chunk)
    after = path.stat()
    if (before.st_dev, before.st_size, before.st_mtime_ns, before.st_ino) != (after.st_dev, after.st_size, after.st_mtime_ns, after.st_ino):
        raise ASRError('Original audio changed while preparing ASR. Next: co asr --help')
    return value.hexdigest(), (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)


def merge(completed: list[dict]) -> str:
    """Keep all raw words in order; text alone cannot prove duplicate speech."""
    return '\n'.join(segment['text'] for segment in completed)


@contextmanager
def _lock(directory: Path):
    descriptor = os.open(directory/'owner.lock', os.O_CREAT | os.O_RDWR | getattr(os, 'O_NOFOLLOW', 0), 0o600)
    try:
        try:
            if os.name == 'nt':
                import msvcrt
                if os.fstat(descriptor).st_size == 0:
                    os.write(descriptor, b'\0')
                os.lseek(descriptor, 0, os.SEEK_SET)
                msvcrt.locking(descriptor, msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            raise ASRError('This ASR job is already running; wait before resuming. Next: co asr --help') from None
        yield
    finally:
        os.close(descriptor)


def run(source: Path, duration: float, provider: str, language, model,
        transcribe, *, resume: str | None = None, progress=None) -> dict:
    identifier = resume or str(uuid4())
    directory = _directory(identifier)
    try:
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        directory.parent.chmod(0o700)
        directory.parent.parent.chmod(0o700)
        directory.chmod(0o700)
        with _lock(directory):
            return _execute(source, duration, provider, language, model, transcribe,
                            identifier, directory, resume=resume, progress=progress)
    except OSError:
        raise ASRError('Cannot access local ASR progress. Next: co asr --help') from None


def _execute(source, duration, provider, language, model, transcribe,
             identifier, directory, *, resume, progress):
    try:
        digest, original = _digest(source)
    except OSError:
        raise ASRError('Cannot read original audio; no upload started. Next: co asr --help') from None
    if resume:
        state = load(resume)
        if state['sha256'] != digest:
            raise ASRError('Audio changed; do not resume this job with another file. Next: co asr --help')
        if state['duration'] != duration:
            raise ASRError('Audio duration differs from the saved job; original and partial text are kept. Next: co asr --help')
        if state['provider'] != provider or state['language'] != language or state['model'] != model:
            raise ASRError('Resume must keep the recorded provider, language and model. Next: co asr --help')
    else:
        state = {'version': 1, 'sha256': digest, 'provider': provider, 'language': language, 'duration': duration,
                 'model': model, 'segments': windows(duration), 'completed': []}
    try:
        _save(directory, state)
    except OSError:
        raise ASRError('Cannot save local ASR progress; no upload started. Next: co asr --help') from None
    try:
        for index in range(len(state['completed']), len(state['segments'])):
            start, end = state['segments'][index]
            if progress:
                progress(index + 1, len(state['segments']))
            with tempfile.TemporaryDirectory(prefix='segment-', dir=directory) as temporary:
                audio = Path(temporary)/'audio.wav'
                export_window(source, audio, start, end)
                current = source.stat()
                if (current.st_dev, current.st_ino, current.st_size, current.st_mtime_ns) != original:
                    raise ASRError('Original audio changed during preparation. Next: co asr --help')
                if not 0 < audio.stat().st_size <= MAX_AUDIO_BYTES:
                    raise ASRError('Unexpected prepared audio size. Next: co asr --help')
                text = transcribe(audio)
            candidate = {**state, 'completed': state['completed'] + [{'start': start, 'end': end, 'text': text}]}
            _save(directory, candidate)
            state = candidate
    except (ASRError, OSError, KeyboardInterrupt) as error:
        reason = str(error) if isinstance(error, ASRError) else 'Local audio/progress operation did not complete.'
        raise ASRInterrupted(identifier, state['completed'], cancelled=isinstance(error, KeyboardInterrupt), reason=reason) from None
    return {'provider': provider, 'text': merge(state['completed']), 'job_id': identifier,
            'segments': state['completed'], 'boundary_overlap_seconds': 2.0}
