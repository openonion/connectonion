---
description: co rem 1.9.1b5 builds the first run's coding-session window once, over the widest range any page needs.
tags: [REM, Performance]
---

# A cache that forgets when asked for more

1.9.1b4 kept the scan of your coding sessions for the whole first run, so each
person would not pay three minutes to re-read them. People still waited.

The cache remembered one window. A person asked for six months; an
organisation, and the worker fetching older mail in the background, asked for
two years. A wider request found the cached window too short, threw it away
and scanned again, behind the same lock everyone else was waiting on. Then the
next person asked for six months, and the next organisation for two years.

1.9.1b5 builds the window once, over two years, and lets every page take the
part it needs. The background mail worker stopped asking for sessions at all;
it was only ever there for mail.
