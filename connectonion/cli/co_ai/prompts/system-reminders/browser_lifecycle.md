---
name: browser-lifecycle
triggers:
  - tool: open_browser
---

<system-reminder>
When `open_browser()` reports that the browser is already open and usable, do not reopen it. Continue operating the current browser page directly.

Only force a fresh browser context when the current browser is stale, unusable, or the user explicitly asks for a fresh browser. A forced reopen closes the previous server-side browser context first, while preserving login state through the persistent browser profile.

Leave the browser open after a successful login so the user can continue using the logged-in page in follow-up turns.
</system-reminder>
