# The Workroom Lost the Conversation

During the 1.7 beta review, I opened a Claude Code Workroom and saw all the
signs of a healthy run. The header said Working. A green dot moved beside the
current task. Safe tool summaries arrived in order. But the middle of the room
was empty. I could not see what I had asked Claude to do, or what Claude had
said back.

Codex did not have this problem, which initially made the bug look like a small
Claude rendering omission. Following the events backwards told a different
story. The UI had quietly defined “conversation” as “the messages on Codex's
direct-input path.” Claude was streaming perfectly good assistant text, but the
shared Workroom had no shared definition of a provider message.

The tempting fix was to make the UI recognize one more provider. That would
have filled today's blank space and preserved tomorrow's architecture bug. We
instead moved the decision to the boundary where provider output first becomes
OIP state. Codex and Claude now identify the same two facts—the user's request
and the provider's attributed reply—with the same message contract. The
Workroom only has to display the truth it receives.

That raised the harder question: what counts as a reply? Claude's stream mixes
visible prose with thinking blocks, tool inputs, and raw tool output. Sending
everything would make the room feel busy, but it would also expose material the
user did not ask to read. We chose the narrower boundary: only attributed text
becomes conversation. Tool work remains visible through its short summary, and
private reasoning remains private. Stable message identities also let a
reconnect replay events without making Claude appear to repeat itself.

The final browser view looks almost uneventful: a task, a Working state, one
user bubble, and one Claude reply. That calm result is the point. A unified
client does not make every provider pretend to have the same controls. It gives
the facts they share one honest path, and leaves provider-specific capabilities
at the edges where they belong.
