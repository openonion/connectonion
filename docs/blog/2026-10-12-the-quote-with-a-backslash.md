---
description: The b16 release test found a fake secret in the session copy. It was harmless, and it showed that a real one written by a tool call would have gone out too.
tags: [Handoff, Security]
---

# The quote with a backslash

Every release of `co handoff` ends with a real handoff between two of our own
machines, and we read what arrives. This time the session copy on the receiving
side contained a string shaped like a Google client secret.

It was a fake, the one our own tests use to check that secrets are removed. But
it should not have survived, and the reason it did was not a fake. When an AI
writes a file, the copy records the call as JSON, so every quote inside the file
is preceded by a backslash. Our pattern for `"password": "..."` expected a quote,
found a backslash, and let it through. A real credentials file written by a tool
call would have gone out the same way.

The pattern now allows any number of backslashes before a quote. Run on the
whole three-day session this was built in, nothing secret-shaped is left.

The test that found it was not a unit test. It was reading the output of a real
run, which is where a fake secret looks exactly like a real one.
