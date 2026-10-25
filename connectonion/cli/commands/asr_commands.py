"""Generic ASR command; reads no audio or account until explicitly invoked."""
import json
from pathlib import Path
from typing import Optional

import typer


def transcribe_audio(
    audio: Path = typer.Argument(..., help='Existing audio file; long recordings are automatically split locally'),
    provider: Optional[str] = typer.Option(None, '--provider', help='codex (default) or connectonion; overrides ASR_PROVIDER for this call'),
    language: Optional[str] = typer.Option(None, '--language', help='Language hint, such as zh or en; otherwise auto-detect'),
    json_out: bool = typer.Option(False, '--json', help='Return provider and text as JSON, or ok=false on failure'),
    resume: Optional[str] = typer.Option(None, '--resume', help='Job ID from an interrupted result; reuse completed parts of the same audio'),
):
    """Uploads one audio file for Codex or ConnectOnion cloud transcription.

    Default: existing file-backed Codex ChatGPT login. Uses the unofficial
    Codex Desktop dictation endpoint, not local recognition or a free API.
    No codex-asr installation is needed. ConnectOnion uses co auth and credits.
    Requires FFmpeg (ffprobe/ffmpeg) for local audio preparation. Long recordings
    use eight-minute windows, saved progress and ordered raw part transcripts.
    Interrupted jobs retain raw part transcripts locally; --resume continues.
    No login changes or provider fallback. No word timestamps or speaker labels.
    """
    from ...audio_asr import ASRError, ASRInterrupted, asr, request_provider
    try:
        chosen = request_provider(provider, resume)
        typer.echo(f'ASR selected: {chosen}; processing destination: ' +
                   ('ChatGPT (unofficial endpoint).' if chosen == 'codex' else 'OpenOnion for cloud processing.'), err=True)
        result = asr(audio, provider=provider, language=language, resume=resume,
                     progress=lambda part, total: typer.echo(f'ASR part {part}/{total}', err=True))
    except ASRError as error:
        if json_out:
            details = ({'job_id': error.job_id, 'completed_segments': error.completed_segments,
                        'partial_text': error.partial_text} if isinstance(error, ASRInterrupted) else {})
            typer.echo(json.dumps({'ok': False, 'error': str(error), **details}, ensure_ascii=False))
        else:
            typer.echo(str(error), err=True)
        raise typer.Exit(getattr(error, 'exit_code', 1)) from None
    typer.echo(json.dumps({'ok': True, **result}, ensure_ascii=False) if json_out else result['text'])
