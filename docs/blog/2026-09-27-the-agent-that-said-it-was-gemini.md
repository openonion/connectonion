# The agent that said it was Gemini

We gave an agent one instruction: your name is Zephyr. We hosted it the way
every deployed agent is hosted, sent it one message, "What is your name?",
and it answered "Gemini".

The instruction never reached the model. A hosted session starts as nothing
but a session id, and when an agent resumed a session it took the stored
messages exactly as they were. For a new session that was an empty list, so
the first turn went out with the user's message and no system prompt. The
second turn continued from what the first had stored, which still had no
system prompt, and so did every turn after that. Every conversation with a
hosted agent, over HTTP, WebSocket, a chat channel or the scheduler, was a
conversation with the bare model.

The local path never had this problem. An agent used directly seeds its first
turn with its system prompt, which is why it went unnoticed: the agent
behaved correctly on the developer's machine and forgot who it was on the
server.

The fix is a few lines where a session is resumed: if the conversation does
not start with the agent's instructions, put them first. That also repairs
sessions that were saved while this was broken, so an existing conversation
picks up its instructions on its next turn. The test sends the same question
through the real hosting path to a model: before the fix, "Gemini"; after,
"Zephyr".
