# ASR: one capability, two providers

Requires the **1.9.3rc23 preview** and FFmpeg, including `ffprobe`, even for
short files. Stable 1.9.2 does not include `co asr`. The
[package](https://pypi.org/project/connectonion/1.9.3rc23/) and
[GitHub prerelease](https://github.com/openonion/connectonion/releases/tag/v1.9.3rc23)
are published. Install this exact preview without changing the stable recommendation:

```bash
python -m pip install --upgrade 'connectonion==1.9.3rc23'
brew install ffmpeg
```

The FFmpeg installation example is for macOS. On other platforms install
`ffmpeg` and `ffprobe` with your package manager and put both on PATH.

```bash
co asr recording.m4a --language zh
co asr recording.m4a --json
co env set ASR_PROVIDER connectonion
co asr recording.m4a
co asr recording.m4a --provider codex
co asr recording.m4a --resume JOB_ID
```

Replace `recording.m4a` with your existing audio file. The default provider is
`codex`; `ASR_PROVIDER` in co's existing selected env file changes it, and
`--provider` overrides it once. No separate config file or server is needed.
`co --env-file /path/to/settings.env asr recording.m4a` selects a specific co
configuration through the existing CLI. Python callers configure their process
environment or pass the provider explicitly.

```python
from connectonion import asr

result = asr("recording.m4a", provider="codex", language="zh")
print(result["text"])
```

Both providers upload audio. Codex uses your existing file-backed ChatGPT login
under `$CODEX_HOME/auth.json` or `~/.codex/auth.json`. It does not refresh or
modify that file, ask you to paste a token, or send the token to OpenOnion.
Keychain-only Codex credentials and API-key-only login are not supported by this
adapter. If file-backed login is missing or expired, run `codex login` and check
your Codex credential-store configuration. Installing Codex alone does not imply
that ASR access or unlimited subscription usage is available.

ConnectOnion uses the existing `transcribe()` API, co authentication and credits.
`ASR_MODEL` may select a `co/` model, otherwise the SDK default applies. This
setting applies only to the ConnectOnion provider. Existing `transcribe()` calls
retain their original behavior.

No provider fallback or automatic retry occurs. The original file is preserved.
Text goes to stdout and destination/progress to stderr. Short direct requests
return `{ok, provider, text}` with `--json`; long recordings also return a
`job_id` and raw `segments` with source-window start/end offsets. Those offsets
are not word-level timestamps. Errors omit upstream response bodies.

## Long meetings and interrupted work

There is no 50 MiB input-file limit. Install FFmpeg (`ffprobe` and `ffmpeg`) for
local inspection and conversion. For example on macOS, `brew install ffmpeg`.
WAV, MP3, M4A/MP4, FLAC, Ogg and WebM can go directly to the provider when short;
other decodable formats are converted locally. There is no upload just to
discover duration.

Long audio is processed one eight-minute window at a time with two seconds of
boundary overlap, converted to 16kHz mono PCM. A three-hour meeting becomes
23 requests rather than a rejected whole file. Only the prepared individual
request has an internal size budget; the original can be larger. The upstream
project's eleven-minute recommendation is not an official Codex limit. This
window size is a conservative implementation choice, not a service guarantee.

Completed raw transcripts are atomically checkpointed in private, owner-only
directories at `~/.co/asr/jobs/JOB_ID/state.json` (or under `AGENT_CONFIG_PATH`).
These local transcript files are plaintext; original audio is not copied into
the checkpoint. Temporary converted windows are removed after each part. Delete
the job directory when you no longer need its saved transcripts/recovery.

On interruption, `--json` reports `job_id`, `completed_segments` and
`partial_text`. Resume with the same original audio and the returned ID:

```bash
co asr recording.m4a --resume JOB_ID --json
```

Resume verifies the original's streamed SHA-256, keeps the recorded provider,
model and language even if default configuration changed, and skips already
checkpointed parts. A second process cannot run the same job simultaneously.
An uncertain request or a failed checkpoint write may require submitting that
one part again; remote exactly-once billing is not promised. No other provider
is invoked to conceal a failure.

The returned text concatenates raw parts in order and preserves repeated words;
two-second boundary overlap may repeat speech. Text similarity alone cannot
prove that a repetition is accidental, so this layer never silently deletes it.
Raw part transcripts remain separate; any later AI cleanup is another version,
not an overwrite. Empty text
can represent silence. No speaker labels, word timestamps or automatic REM
ingestion. Network timeout is 15 seconds to connect and 300 seconds of network
inactivity per request. Keep originals to check omissions or recognition errors.

## Protocol source and experimental status

The Codex provider is an independent Python implementation informed by
[Wangnov/codex-asr](https://github.com/Wangnov/codex-asr), an MIT-licensed Rust
project. It uses `https://chatgpt.com/backend-api/transcribe` with multipart
audio, bearer authentication, an optional account routing header and a JSON text
response. This is the unofficial Codex Desktop dictation endpoint, not the
public OpenAI transcription API or Codex app-server realtime. Availability and
subscription entitlement are not guaranteed and may change.

No external `codex-asr` binary, Rust runtime, token broker or REST wrapper is
installed. Protocol compatibility tests use synthetic credentials and HTTP;
those tests do not establish live account access or recognition quality.
