# Audio Transcription

Convert audio files to text using Gemini's multimodal capabilities. Simple one-function interface for transcription.

## Quick Start

```python
from connectonion import transcribe

# Simple transcription (uses OpenOnion managed keys)
text = transcribe("meeting.mp3")
print(text)

# With your own Gemini API key
text = transcribe("meeting.mp3", model="gemini-3-flash-preview")
```

That's it! One function for audio-to-text.

## With Context Hints

Improve accuracy for domain-specific terms:

```python
# Technical meeting with specific names
text = transcribe(
    "standup.mp3",
    prompt="Technical AI discussion. Names: Aaron, Lisa. Terms: ConnectOnion, OpenOnion"
)

# Medical transcription
text = transcribe(
    "consultation.mp3",
    prompt="Medical consultation. Terms: hypertension, metformin, CBC"
)
```

## With Timestamps

```python
text = transcribe("podcast.mp3", timestamps=True)
# Output: "[00:00] Welcome to the show...\n[00:15] Today we're discussing..."
```

## Real Examples

### Meeting Minutes

```python
def get_meeting_minutes(audio_path: str) -> str:
    """Transcribe and summarize a meeting."""
    from connectonion import transcribe, llm_do

    # Step 1: Transcribe
    transcript = transcribe(audio_path, prompt="Business meeting")

    # Step 2: Summarize
    summary = llm_do(
        transcript,
        system_prompt="Extract action items and key decisions as bullet points."
    )
    return summary
```

### Voice Notes Processing

```python
from pathlib import Path

def process_voice_notes(folder: str) -> list[str]:
    """Transcribe all voice notes in a folder."""
    from connectonion import transcribe

    results = []
    for audio in Path(folder).glob("*.mp3"):
        text = transcribe(str(audio))
        results.append(f"# {audio.stem}\n{text}")
    return results
```

### Use as Agent Tool

```python
from connectonion import Agent, transcribe

def transcribe_audio(file_path: str) -> str:
    """Transcribe an audio file to text."""
    return transcribe(file_path)

agent = Agent("assistant", tools=[transcribe_audio])
result = agent.input("Transcribe the file meeting.mp3 and summarize it")
```

## Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `audio` | str | required | Path to audio file |
| `prompt` | str | None | Context hints for accuracy |
| `model` | str | "co/gemini-3-flash-preview" | Model to use |
| `timestamps` | bool | False | Include timestamps in output |

## Supported Formats

- WAV, MP3, AIFF, AAC, OGG, FLAC, M4A, WebM

**Token cost:** 32 tokens per second of audio (1 minute = 1,920 tokens)

## Models

```python
# OpenOnion managed keys (default - no API key needed)
transcribe("audio.mp3", model="co/gemini-3-flash-preview")
transcribe("audio.mp3", model="co/gemini-2.5-flash")

# Your own Gemini API key (set GEMINI_API_KEY)
transcribe("audio.mp3", model="gemini-3-flash-preview")
transcribe("audio.mp3", model="gemini-2.5-flash")
```

## Error Handling

```python
from connectonion import transcribe

try:
    text = transcribe("nonexistent.mp3")
except FileNotFoundError:
    print("Audio file not found")
except ValueError as e:
    print(f"API error: {e}")
```

## Comparison with Agent

| Feature | `transcribe()` | `Agent()` |
|---------|----------------|-----------|
| Purpose | Audio to text | Multi-step workflows |
| Input | Audio files | Text prompts |
| Output | Plain text | Agent responses |
| Best for | Transcription | Complex tasks |

```python
# Use transcribe() for audio-to-text
text = transcribe("meeting.mp3")

# Use Agent for complex workflows with multiple tools
agent = Agent("assistant", tools=[search, calculate])
result = agent.input("Research and analyze...")
```

## Next Steps

- Learn about [llm_do()](concepts/llm_do.md) for one-shot LLM calls
- Explore [Agents](concepts/agent.md) for multi-step workflows
- See [Tools](concepts/tools.md) for extending agents
