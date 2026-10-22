---
description: Preparing an expense bot for the inbox exposed three places where an original file could become only the word [file].
tags: [Inbox, Feishu, Reliability]
---

# The file became a word

We were preparing to move an expense assistant to the framework's inbox when
an invoice archive stopped the rollout. The original message had a file key
and a name. A program taking it from the queue would receive `[file]`, marked
as text. It had no reference with which to retrieve the archive.

The queue had faithfully stored what the provider gave it. The loss happened
earlier: the Feishu adapter left the message kind at its default and reduced
rich posts to their text runs. Some of the posts we inspected carried their
PDFs in a separate `files` list, beside the visible paragraphs. Those files
never entered the normal record. A private replay of ten original message
snapshots contained 135 resource references; the old adapter exposed zero.

Keeping the whole provider payload would have brought unrelated raw data into
every consumer's input. The inbox already keeps that payload in its journal
when explicitly asked. We kept that boundary and carried a smaller record
through the queue: the original resource type, key and name. Typed sender IDs
travel beside the existing sender key, so an application can verify its
app-scoped binding. A post's title travels with its words; it can contain the
purpose of the expense even when the paragraph contains only an image.

That made the CLI tests pass. Then we followed a file into the Host's actual
agent input and found the same loss again. The Host passed only the text,
turning the intact record back into `[file]`. Its regression test failed until
non-text messages carried their normal JSON record through that final step.
Plain text keeps its ordinary input, and sender permissions stay unchanged.

A crash-recovery regression exposed another gap. The listener remembers a conversation
before writing its first message. Recovery looked only at the journal, so a
crash between those writes could leave a remembered conversation unqueried.
It now includes those already recorded conversations under the same recovery
boundary.

The final local inbox and Host run passed 436 tests. The ten-message replay
preserved all 135 references through claims, matched live and history
normalization, and accepted no duplicate redeliveries. That checks the message
path. Downloading those originals, extracting an archive and submitting an
expense still need their own acceptance evidence on the application server.

After publication, see the [Feishu and Lark consumer contract](https://docs.connectonion.com/cli/feishu)
and [rc15 installation and release scope](https://docs.connectonion.com/releases/1.9.3rc15).
