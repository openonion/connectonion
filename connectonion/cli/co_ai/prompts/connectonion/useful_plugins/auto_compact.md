# auto_compact

Summarise the conversation before it overflows the context window.

Fires on `after_llm`. When context usage reaches **90%** and there are at least
8 messages, it replaces the older messages with an LLM-written summary and keeps
the system prompt, the summary, and the **last 5 messages**.

```
COMPACT_THRESHOLD = 90
```

The summarising call uses a fast, cheap model rather than the agent's own — the
job is compression, not reasoning, and paying the agent's model rate for it on
every long session adds up.

## Why 90 and not 100

Compaction itself needs room to run. Waiting for the window to be full means the
summarisation call has nowhere to go.

## What survives

The system prompt, always. The summary, in place of what it replaced. The last
five messages verbatim, because recent turns are the ones the next reply
actually depends on.

## What it costs you

Detail. Anything older than the last five messages exists only as the summary
said it did. For work where the early conversation matters — a long debugging
session, a spec being assembled — start a fresh session rather than letting it
compact.
