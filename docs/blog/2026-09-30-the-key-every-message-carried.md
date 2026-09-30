# The key every message carried

This morning the notebook learned to write project pages from what the owner
types to his coding agents. The reader it used had one rule for Codex: a message
the person typed has three keys, `content`, `role` and `type`. Anything that also
carried `internal_chat_message_metadata_passthrough` was the client talking to
itself, AGENTS.md and environment blocks and goal reminders. Over thirty days of
the Codex CLI that rule was exact.

Then the skill-usage count (#1976) went through the same sessions and found
the number that did not fit. Of 13,065 messages in the user slot over 90 days,
12,285 were dropped as injected. The owner does almost all his Codex work in
Codex Desktop, and Desktop puts that key on every message it takes, the ones he
types included. The rule had not been wrong about the CLI. It was never checked
against the app he actually uses, so 94% of his Codex words never reached a
page.

The fix had to tell typed from injected by something real, so we opened the
Desktop rollouts read-only and counted field names, never the text. The
passthrough holds `turn_id`, `create_time` and `content_item_kinds`, and the
last one does the work. A message he typed lists only `user.text` or
`user.image`. What the client adds names itself: `agents_md.instructions`,
`environments.environment_context`, `plugins.recommendations`,
`goal.internal_context`. Some messages have no kinds at all, and we needed a
way to check them without reading them. The owner writes mostly in Chinese: 64%
of the typed messages contain Chinese characters, and only 13% of the no-kinds
ones do. So a message with no kinds counts as the client's, and is skipped.

The counts turned up two more surprises. The 780 Desktop messages the old
reader did keep, the only ones with the plain three-key shape, were not typed in
Desktop. Every one came from a Claude Code session Desktop had imported, and co
rem already reads that session from Claude Code, so each page was getting those
words twice. The other surprise was subagent threads, the approval reviewer and
spawned workers. Their user slot is text the agent wrote, sometimes with the
parent's messages copied in, and it is labelled `user.text` like the real
thing. Those threads are now skipped the way Claude Code sidechains already
were.

After the change, on his machine and counting only, Codex Desktop gives 774
messages over 90 days where it gave 112. Those 112 were all copies of Claude
Code sessions. Of the new ones, 670 were typed in `~/projects`, and the
workspace attribution from this morning places 632 of them in a repository by
their own tool calls, since Desktop threads carry the same `turn_context` and
exec calls the CLI does. The 340 workspace messages that stayed out this morning
are down to 67. The 312 we had blamed on Desktop threads with no tool calls were
the imported copies. Their Claude Code originals are placed by Claude Code's
own tool calls.

The lesson is about where an allowlist gets its sample. Recognising the typed
shape rather than the injected one was the right call, because it fails closed.
But the sample was one client, and the owner lives in the other one. Failing
closed kept the notebook free of harness text, and it also cost 94% of his
Codex words without a single warning. So the reader now calls a user-slot
message in a shape it has never seen unfamiliar, whether or not it carries the
passthrough key. Twenty of those in one pass and it says the format has moved.
