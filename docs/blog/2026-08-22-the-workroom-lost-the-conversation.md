# The Workroom Lost the Conversation

A Workroom could already show that Claude Code was running. It could list safe
tool summaries and files, yet the two most basic parts of the exchange were
missing: what the user asked and what Claude answered. The same UI appeared to
work for Codex only because Codex had a separate message path. We had built one
Workroom with two different definitions of a conversation.

The fix belongs at the provider boundary. After a native Codex turn actually
starts, Core now publishes the initiating user message with the invocation that
owns it. Claude Code publishes the same initiating message and the text blocks
from its assistant stream. Both providers therefore use the same OIP
`provider_message` contract, and clients no longer need to infer conversation
content from tool calls or terminal output.

That boundary also protects information that should not become interface copy.
Claude thinking blocks are not assistant messages. Tool inputs and raw output
are not assistant messages either. The adapter extracts only attributed text,
bounds it through the shared event constructor, assigns stable native IDs when
available, and deduplicates normalized updates. A reconnect can replay the same
provider event without duplicating the transcript.

The focused provider suite passes 153 tests. The paired O Chat browser test
shows a Claude Code Workroom with its task, Working state, current summary,
user message, and assistant message. It also verifies that the UI does not
invent Codex's direct composer for a provider that has not exposed that input
capability.

A unified client does not require every provider to have identical controls.
It requires identical facts to travel through one contract, while native
capabilities remain honest at the edges.
