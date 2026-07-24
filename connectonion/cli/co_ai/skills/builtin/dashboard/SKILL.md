---
name: dashboard
description: Update the agent's Home dashboard. Use when the user says "update my dashboard", "redesign my home", "put X on the dashboard", or "/dashboard".
---

# Dashboard Skill

The agent's Home is a single file, `dashboard.html`, in the project root. OChat renders it in a sandboxed iframe beside the chat and re-reads it after every run. You edit it with your normal file tools (Read, Edit, Write, Bash) — there is no special API.

## Instructions

1. **Read `dashboard.html` first** so you preserve its structure and styles before changing anything.
2. **Make the smallest edit that satisfies the request** — change the data or add a section; don't rewrite the whole file unless the user asks for a redesign.
3. **Keep it visual, not textual.** Lead with big numbers, generous whitespace, and clear action buttons. A dashboard is a glanceable Home, not a document.
4. **Write the file** and stop. OChat picks up the change automatically after the run.

## Action buttons — the one contract

A button that runs something MUST be a real, user-invocable skill, wired like this:

```html
<button data-ochat-skill="daily-brief">Build today's brief</button>
```

- The `data-ochat-skill` value is the exact skill name; OChat validates it and runs `/daily-brief` as a visible chat turn.
- Optional arguments: `data-ochat-skill="meeting-prep" data-ochat-args="2pm sync"` → runs `/meeting-prep 2pm sync`.
- Use an **outcome-oriented label** ("Prepare my next meeting"), not the raw skill name.
- Only reference skills that actually exist. Never invent skill names, and don't add buttons for internal/bootstrap skills.

## Rules

- One file: `dashboard.html`. No sidecar JSON, no build step.
- Keep the responsive layout and `prefers-color-scheme` dark mode intact.
- Do not add `<script>` tags or inline `onclick` handlers — OChat strips all scripting; only the `data-ochat-skill` button contract works.
- Keep styles inline in the file (external URLs are blocked in the sandbox).
