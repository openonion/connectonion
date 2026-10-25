---
title: ASR is a capability, not a device
date: 2026-10-26
tags: [Audio, CLI, Providers]
---

# ASR is a capability, not a device

A watch recorder needs speech recognition, but speech recognition should not
belong to the watch integration. The same file may come from a phone, a meeting
recorder or an agent workflow. Requiring each source to choose its own model,
authentication and transcript format repeats the hardest part of the experience.

The proposed ConnectOnion ASR preview gives these sources one capability:
`co asr recording.m4a`. Codex is the default; the existing co configuration can
select ConnectOnion's own transcription instead. An explicit provider override
affects one call. Provider failure never changes where an audio file is sent.

We considered installing the separate Rust codex-asr CLI, using the Codex
app-server realtime protocol, or requiring a local Whisper model. The owner
chose an integrated Python adapter, informed by
[Wangnov/codex-asr](https://github.com/Wangnov/codex-asr), so no extra ASR command,
runtime or local proxy needs installation. Existing `transcribe()` users keep
their API; the new provider selector does not silently change their behavior.

The Codex adapter uploads the selected audio to an unofficial Desktop dictation
endpoint using the local file-backed login. It is cloud recognition, and a
successful local adapter does not establish permanent account entitlement or
unlimited use. One synthesized short English sentence completed a live request;
long recordings, mixed languages and recognition quality still need evaluation.
An original recording must survive every processing failure.

A file-size guard also turned out to be the wrong product boundary: a three-hour
meeting should not become unusable because one HTTP request has a budget. Local
FFmpeg windows make that a request concern. Each completed part is saved before
the next starts, so a failed request does not restart the whole meeting. We also
removed a tempting text-similarity merge: two matching phrases can be genuine
repeated speech. Raw words remain in order, including possible boundary overlap;
any later cleaned-up account is a separate version.

This post is a release draft. The candidate is not advertised as available until
the matching PyPI artifact and GitHub prerelease have been verified. The
[ASR configuration draft](/asr.md) records the workflow and limitations.
