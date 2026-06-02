---
name: browser-lifecycle
triggers:
  - tool: open_browser
---

<system-reminder>
Opening a browser closes any previous server-side browser context first, while preserving login state through the persistent browser profile.

When the login or browser flow succeeds, fails, or cannot continue, call `close_browser` before your final response so the current browser process is released.
</system-reminder>
