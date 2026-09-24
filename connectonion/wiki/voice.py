"""Opt-in local whisper.cpp transcription; never downloads or falls back to cloud."""

import shutil
import subprocess
import tempfile
from pathlib import Path

from .files import WikiError


def transcribe(audio: Path, model: Path) -> str:
    executable = shutil.which('whisper-cli')
    if not executable:
        raise WikiError('Local transcription requires whisper-cli (whisper.cpp) on PATH')
    if audio.suffix.lower() != '.wav' or not audio.is_file() or not model.is_file():
        raise WikiError('Provide an existing WAV file and local whisper.cpp model file')
    with tempfile.TemporaryDirectory(prefix='co-wiki-voice-') as temporary:
        output = Path(temporary) / 'transcript'
        try:
            result = subprocess.run([executable, '-m', str(model.resolve()), '-f', str(audio.resolve()),
                                     '-otxt', '-of', str(output)], capture_output=True, timeout=120)
        except subprocess.TimeoutExpired as error:
            raise WikiError('Local transcription timed out; review remains pending') from error
        path = output.with_suffix('.txt')
        if result.returncode or not path.is_file():
            raise WikiError('Local transcription failed; review remains pending')
        text = path.read_text(encoding='utf-8').strip()
        if not text:
            raise WikiError('Local transcription was empty; review remains pending')
        return text
