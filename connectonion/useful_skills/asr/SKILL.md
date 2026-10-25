---
name: asr
description: Transcribe an existing audio file with configurable Codex or ConnectOnion cloud ASR.
---

# ASR

Read `co asr --help` for the current options, processing destination and limits.
Both providers upload audio; the default is Codex using the local file-backed
ChatGPT login. `co env set ASR_PROVIDER connectonion` selects ConnectOnion.
`--provider` overrides one call. There is no automatic fallback.

Use an existing user-selected audio file, inspect the actual result, and keep
the original. `--json` separates success (`ok`, `provider`, `text`) from failures.
Empty text can represent silence. Failures name a recovery command; don't
invent a transcript, silently choose another provider or claim memory ingestion.

No timestamps or automatic long-recording segmentation in this preview. The
unofficial Codex endpoint can change; a login does not guarantee ASR entitlement.
See `co asr --help` before execution rather than guessing parameters.
