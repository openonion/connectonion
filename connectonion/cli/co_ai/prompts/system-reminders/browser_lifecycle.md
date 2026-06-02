---
name: browser-lifecycle
triggers:
  - tool: open_browser
---

<system-reminder>
Opening a browser closes any previous server-side browser context first, while preserving login state through the persistent browser profile.

Leave the browser open after a successful login so the user can continue using the logged-in page in follow-up turns.

Do not call `close_browser` automatically after successful login. Call it only when the user explicitly asks to close the browser or the active browser flow is abandoned and cannot continue.
</system-reminder>
