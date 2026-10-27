"""Local, bounded-memory audio inspection and one-window conversion."""
import math
import os
from pathlib import Path
import shutil
import subprocess

from .audio_asr import ASRError

WINDOW_SECONDS = 480.0
OVERLAP_SECONDS = 2.0


def _tool(name: str) -> str:
    found = shutil.which(name)
    if not found:
        raise ASRError(f'{name} is required for audio inspection/splitting. Install FFmpeg. Next: co asr --help')
    return found


def _run(arguments: list[str], timeout: int) -> bytes:
    env = {key: os.environ[key] for key in ('PATH', 'TMPDIR', 'SYSTEMROOT') if key in os.environ}
    try:
        result = subprocess.run(arguments, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                stderr=subprocess.DEVNULL, env=env, timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired):
        raise ASRError('Local audio preparation failed or timed out. Next: co asr --help') from None
    if result.returncode:
        raise ASRError('Cannot decode this audio file with FFmpeg. Next: co asr --help')
    return result.stdout


def probe_duration(path: Path) -> float:
    """Read duration only; file/pipe protocols prevent network playlist inputs."""
    import json
    raw = _run([_tool('ffprobe'), '-v', 'error', '-protocol_whitelist', 'file,pipe',
                '-select_streams', 'a:0', '-show_entries', 'stream=duration:format=duration',
                '-of', 'json', str(path)], 30)
    try:
        data = json.loads(raw)
        streams = data['streams']
        if not streams:
            raise ValueError('no audio')
        duration = float(streams[0].get('duration', data['format'].get('duration', 'nan')))
        if not math.isfinite(duration) or duration <= 0:
            raise ValueError('invalid duration')
        return duration
    except (ValueError, KeyError, TypeError, IndexError):
        raise ASRError('Cannot determine audio duration. Next: co asr --help') from None


def windows(duration: float) -> list[tuple[float, float]]:
    return [(start, min(duration, start + WINDOW_SECONDS + OVERLAP_SECONDS))
            for start in (index * WINDOW_SECONDS for index in range(math.ceil(duration / WINDOW_SECONDS)))]


def export_window(source: Path, target: Path, start: float, end: float) -> None:
    """Decode just one segment to 16kHz mono PCM; roughly 15 MiB per 8 minutes."""
    _run([_tool('ffmpeg'), '-nostdin', '-v', 'error', '-y',
          '-protocol_whitelist', 'file,pipe', '-ss', str(start), '-i', str(source),
          '-t', str(end-start), '-map', '0:a:0', '-vn', '-ac', '1', '-ar', '16000',
          '-c:a', 'pcm_s16le', str(target)], 180)
    target.chmod(0o600)
