---
description: 1.9.2b17 makes the session copy that travels with a handoff answer drop credentials written through a tool call.
tags: [Release, Handoff, Security]
---

# 1.9.2b17: nothing secret in the copy

When someone takes over your work and asks a question, your agent answers with a
copy of the session, so they can find what the summary left out. That copy has
to leave your keys behind.

This preview closes a gap we found by reading a real copy: a credential the AI
had written into a file, through a tool call, was recorded with escaped quotes
and slipped past. It no longer does. We ran it over the longest session we have
and found nothing secret left in it.
