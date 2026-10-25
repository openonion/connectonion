# ASR: one capability, two providers

```bash
co asr recording.m4a --language zh
co asr recording.m4a --json
co env set ASR_PROVIDER connectonion
co asr recording.m4a
co asr recording.m4a --provider codex
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

No provider fallback or automatic retry occurs. HTTP failure may follow an
upload: retrying can submit the audio again. The command preserves the original
file, prints text to stdout (provider/destination to stderr), and does not save
a transcript or ingest memory. `--json` returns `{ok, provider, text}` for success
and `{ok:false,error}` for ASR validation/provider failures. Upstream response
bodies are omitted from errors; authentication failures give a login next step. Empty text can mean
silence; it is not a reason to invent words.

Accepted containers: WAV, MP3, M4A/MP4, FLAC, Ogg and WebM, nonempty and at most
50 MiB. A supported suffix does not prove a valid container. No automatic
conversion, timestamps, diarization or long-file splitting is promised. The
upstream project recommends splitting files longer than 11 minutes; this preview
does not yet guarantee complete long-meeting transcripts. Network timeout is
15 seconds to connect and 300 seconds of network inactivity. Original files
must remain available for checking omissions and recognition errors.

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
