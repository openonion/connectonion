"""
Purpose: Audio transcription utility using Gemini API
LLM-Note:
  Dependencies: imports from [os, base64, pathlib, mimetypes, google.generativeai] | imported by [user code] | tested by [tests/test_transcribe.py]
  Data flow: transcribe(audio, prompt, model) → load audio file → encode base64 → call Gemini API → return text
  State/Effects: reads audio files from disk | makes Gemini API request | no caching
  Integration: exposes transcribe(audio, prompt, model, timestamps) | similar pattern to llm_do()
  Performance: one API call per transcription | files < 20MB use inline, larger use File API
  Errors: raises ValueError if audio file not found | FileNotFoundError for missing files

Audio transcription utility for ConnectOnion framework.

This module provides the `transcribe()` function - a simple interface for
converting audio files to text using Gemini's multimodal capabilities.

Usage:
    >>> from connectonion import transcribe

    # Simple transcription
    >>> text = transcribe("meeting.mp3")

    # With context hints (improve accuracy for domain-specific terms)
    >>> text = transcribe("meeting.mp3", prompt="Technical AI discussion, speakers: Aaron, Lisa")

    # Different model
    >>> text = transcribe("meeting.mp3", model="co/gemini-2.5-flash")

Supported formats: WAV, MP3, AIFF, AAC, OGG, FLAC
Token cost: 32 tokens per second of audio (1 minute = 1,920 tokens)
"""

import os
import base64
import mimetypes
from pathlib import Path
from typing import Optional
import httpx


# MIME type mapping for audio formats
AUDIO_MIME_TYPES = {
    ".wav": "audio/wav",
    ".mp3": "audio/mp3",
    ".aiff": "audio/aiff",
    ".aac": "audio/aac",
    ".ogg": "audio/ogg",
    ".flac": "audio/flac",
    ".m4a": "audio/mp4",
    ".webm": "audio/webm",
}

# Maximum file size for inline audio (20MB)
MAX_INLINE_SIZE = 20 * 1024 * 1024


def _get_mime_type(file_path: Path) -> str:
    """Get MIME type for audio file."""
    suffix = file_path.suffix.lower()
    if suffix in AUDIO_MIME_TYPES:
        return AUDIO_MIME_TYPES[suffix]
    # Fallback to mimetypes library
    mime_type, _ = mimetypes.guess_type(str(file_path))
    return mime_type or "audio/mpeg"


def _get_api_key(model: str) -> str:
    """Get API key based on model."""
    if model.startswith("co/"):
        # Use OpenOnion managed keys
        api_key = os.getenv("OPENONION_API_KEY")
        if not api_key:
            # Try loading from config file
            config_path = Path.home() / ".connectonion" / ".co" / "config.toml"
            if config_path.exists():
                import toml
                config = toml.load(config_path)
                api_key = config.get("auth", {}).get("jwt_token")
        if not api_key:
            raise ValueError(
                "OpenOnion API key required for co/ models. "
                "Run `co auth` to authenticate or set OPENONION_API_KEY."
            )
        return api_key
    else:
        # Use Gemini API key directly
        api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        if not api_key:
            raise ValueError(
                "Gemini API key required. Set GEMINI_API_KEY environment variable."
            )
        return api_key


def transcribe(
    audio: str,
    prompt: Optional[str] = None,
    model: str = "co/gemini-3-flash-preview",
    timestamps: bool = False,
) -> str:
    """
    Transcribe audio file to text using Gemini.

    Args:
        audio: Path to audio file (WAV, MP3, AIFF, AAC, OGG, FLAC)
        prompt: Optional context hints for better accuracy
                (e.g., "Technical AI discussion, speakers: Aaron, Lisa")
        model: Model to use (default: co/gemini-3-flash-preview)
        timestamps: If True, include timestamps in output

    Returns:
        Transcribed text

    Examples:
        >>> # Simple transcription
        >>> text = transcribe("meeting.mp3")

        >>> # With context hints
        >>> text = transcribe("meeting.mp3", prompt="Fix: ConnectOnion, OpenOnion")

        >>> # With timestamps
        >>> text = transcribe("podcast.mp3", timestamps=True)

    Raises:
        FileNotFoundError: If audio file doesn't exist
        ValueError: If API key is missing or invalid audio format
    """
    # Validate file exists
    file_path = Path(audio)
    if not file_path.exists():
        raise FileNotFoundError(f"Audio file not found: {audio}")

    # Get file info
    file_size = file_path.stat().st_size
    mime_type = _get_mime_type(file_path)

    # Read and encode audio
    with open(file_path, "rb") as f:
        audio_bytes = f.read()
    audio_base64 = base64.standard_b64encode(audio_bytes).decode("utf-8")

    # Build prompt
    if timestamps:
        system_prompt = "Transcribe this audio with timestamps in [MM:SS] format."
    else:
        system_prompt = "Transcribe this audio accurately."

    if prompt:
        system_prompt += f" Context: {prompt}"

    # Get API key and model name
    api_key = _get_api_key(model)
    actual_model = model[3:] if model.startswith("co/") else model

    # Use OpenOnion proxy for co/ models, direct Gemini API otherwise
    if model.startswith("co/"):
        return _transcribe_via_openonion(
            audio_base64, mime_type, system_prompt, api_key, actual_model
        )
    else:
        return _transcribe_via_gemini(
            audio_base64, mime_type, system_prompt, api_key, actual_model
        )


def _transcribe_via_gemini(
    audio_base64: str,
    mime_type: str,
    prompt: str,
    api_key: str,
    model: str,
) -> str:
    """Transcribe using Gemini's OpenAI-compatible endpoint."""
    import openai

    client = openai.OpenAI(
        api_key=api_key,
        base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
    )

    response = client.chat.completions.create(
        model=model,
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "input_audio",
                        "input_audio": {
                            "data": audio_base64,
                            "format": mime_type.split("/")[-1],  # e.g., "mp3"
                        },
                    },
                ],
            }
        ],
    )

    return response.choices[0].message.content


def _transcribe_via_openonion(
    audio_base64: str,
    mime_type: str,
    prompt: str,
    api_key: str,
    model: str,
) -> str:
    """Transcribe using OpenOnion proxy (for co/ models)."""
    # Determine API URL
    is_dev = os.getenv("OPENONION_DEV") or os.getenv("ENVIRONMENT") == "development"
    base_url = "http://localhost:8000" if is_dev else "https://oo.openonion.ai"

    # Build request
    request_body = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "input_audio",
                        "input_audio": {
                            "data": audio_base64,
                            "format": mime_type.split("/")[-1],
                        },
                    },
                ],
            }
        ],
    }

    response = httpx.post(
        f"{base_url}/v1/chat/completions",
        json=request_body,
        headers={"Authorization": f"Bearer {api_key}"},
        timeout=120.0,
    )

    if response.status_code != 200:
        raise ValueError(f"Transcription failed: {response.status_code} - {response.text}")

    data = response.json()
    return data["choices"][0]["message"]["content"]
