---
title: Two rollouts, one session
date: 2026-10-26
description: A Codex message id has to name the message, not only its position in a file.
---

REM named a Codex message by its session and byte offset. That looked unique
until someone resumed a conversation. Resumed and forked rollouts can share a
session id, so two files held different messages at the same offset under the
same name. The next extraction saw a familiar id, added nothing, and the newer
message never reached the notebook. Keeping both copies made retention stop
with a citation conflict.

The position was never the identity. The content was. A Codex id now ends with
a short hash of the parsed text, taken before redaction or truncation, so every
reader computes the same value. A copied prefix still collapses to one id;
messages that diverge get two.

Old ids stay readable. Notebooks and retained citations need no migration, and
a page citing an old id still counts as having read that message. When the
same id does arrive with different text, the merge reports the conflict
instead of quietly keeping the first. Two synthetic rollouts sharing a session
id now extract both messages.

This change is on the path to the next 1.9.3 release candidate.
