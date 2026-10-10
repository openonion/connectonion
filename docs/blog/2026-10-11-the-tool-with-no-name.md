---
description: One tool call with an empty name ended a 200-iteration run at step 76. Now a nameless call is answered like any unknown tool, and the run goes on.
tags: [Agent, Reliability]
---

# The tool with no name

A scheduled `co ai` run was 76 iterations into a 200-iteration budget when
it died:

```
BadRequestError: 400 - GenerateContentRequest.contents[1].parts[0]
  .function_response.name: Name cannot be empty.
```

The odd part is that the bad request was ours, not the model's. On the turn
before, Gemini had returned one tool call with an id and no name. We did
what we do with every tool call: wrote it into the conversation history and
answered it. The next request sent that history back, and Gemini refused
all of it because one entry had an empty name. Seventy-six iterations of work
were gone, and nothing could have continued from that history anyway. Every
later request would carry the same empty name.

## Not a retry

The issue proposed catching the 400 and retrying the turn. That treats the
symptom one layer too late. By the time the error comes back, the bad entry
is already in history, so a retry would send it again.

The fix belongs where the call enters our code. Every provider builds a
`ToolCall`, eight places in all, and `ToolCall` now refuses to hold an empty
name. A blank one becomes `unnamed_tool`. From there, nothing special
happens. The executor already knows what to do with a tool that doesn't
exist: it answers "Tool 'unnamed_tool' not found... The tools you can call
are: ...", and the model, given the real list, picks a real one.

## What the test checks

The new test sends a nameless call through the real executor. It checks
that the assistant message going back to the provider has a name in it, and
that the tool result says "not found" and lists the actual tools. It failed
on main and passes now. We have seen this only once in our logs, so we can't
say what makes the model drop the name. We can say that dropping it no
longer costs the whole run.
