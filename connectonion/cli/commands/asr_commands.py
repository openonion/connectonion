"""Generic ASR command; reads no audio or account until explicitly invoked."""
import json
from pathlib import Path
from typing import Optional

import typer


def transcribe_audio(
    audio: Path = typer.Argument(..., help='Existing audio file: WAV, MP3, M4A/MP4, FLAC, Ogg or WebM; up to 50 MiB'),
    provider: Optional[str] = typer.Option(None, '--provider', help='codex (default) or connectonion; overrides ASR_PROVIDER for this call'),
    language: Optional[str] = typer.Option(None, '--language', help='Language hint, such as zh or en; otherwise auto-detect'),
    json_out: bool = typer.Option(False, '--json', help='Return provider and text as JSON, or ok=false on failure'),
):
    """Uploads one audio file for Codex or ConnectOnion cloud transcription.

    Default: existing file-backed Codex ChatGPT login. Uses the unofficial
    Codex Desktop dictation endpoint, not local recognition or a free API.
    No codex-asr installation is needed. ConnectOnion uses co auth and credits.
    Saves no transcript, changes no login and never switches providers on error.
    No timestamps or automatic long-recording segmentation in this preview.
    """
    from ...audio_asr import ASRError, asr, selected_provider
    try:
        chosen = selected_provider(provider)
        typer.echo(f'ASR selected: {chosen}; processing destination: ' +
                   ('ChatGPT (unofficial endpoint).' if chosen == 'codex' else 'OpenOnion for cloud processing.'), err=True)
        result = asr(audio, provider=chosen, language=language)
    except ASRError as error:
        if json_out:
            typer.echo(json.dumps({'ok': False, 'error': str(error)}))
        else:
            typer.echo(str(error), err=True)
        raise typer.Exit(1) from None
    typer.echo(json.dumps({'ok': True, **result}, ensure_ascii=False) if json_out else result['text'])
