---
name: dashboard
description: Update the agent's Home dashboard. Use when the user says "update my dashboard", "redesign my home", "put X on the dashboard", or "/dashboard".
---

# Dashboard Skill

The agent's Home is a single file, `.co/dashboard.html`, beside `.co/skills/`. (Older agents keep theirs in the project root — if `dashboard.html` is there, that is the one being served: edit it where it is, don't create a second one.) OChat renders it in a sandboxed iframe beside the chat and re-reads it after every run. You edit it with your normal file tools (Read, Edit, Write, Bash) — there is no special API.

## Instructions

1. **Read the file first** — `.co/dashboard.html`, or the root `dashboard.html` if that is where this agent's already is — so you preserve its structure and styles before changing anything.
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
- **Only project skills work as buttons** — the ones in `.co/skills/` or `.claude/skills/`. Your personal skills (`~/.co/skills/`) and builtin skills aren't published to clients, so a button for one renders but silently refuses to run. Check the skill's location before wiring it up.

## Filtering a long list

A Home pane that lists thirty skills is a wall. Declare the list filterable and
the client renders the box and does the filtering:

```html
<co-filter target="#skills" placeholder="Filter skills"></co-filter>
<div id="skills">
  <button data-ochat-skill="daily-brief">Build today's brief</button>
  <button data-ochat-skill="meeting-prep">Prepare my next meeting</button>
</div>
```

- `target` is a CSS selector for the container. Its **direct children** are what
  get shown and hidden, so wrap each row in one element.
- Matching is case-insensitive and anywhere in the row's text.
- You write the tag; you never write the behaviour. There is no script to add,
  and adding one would not run.
- If `target` matches nothing, no box is rendered — a filter that filters
  nothing looks like a working control and is not one.

## Sorting a table

Declare the table sortable and the client makes its headers clickable:

```html
<co-table target="#runs"></co-table>
<table id="runs">
  <thead><tr><th>skill</th><th>runs</th></tr></thead>
  <tbody>
    <tr><td>daily-brief</td><td>128</td></tr>
    <tr><td>meeting-prep</td><td>9</td></tr>
  </tbody>
</table>
```

- `target` is a CSS selector for the `<table>`. It needs a `<thead>` and a
  `<tbody>`, or nothing is rendered.
- **Do not label the column types.** Numbers sort as numbers because the cells
  are read, not because you said so — `$1,200`, `30%` and `1,000` all count.
- First click sorts ascending, second descending.
- Sorting and `<co-filter>` compose: one reorders, the other hides.

## Rules

- One file: `.co/dashboard.html`. No sidecar JSON, no build step.
- **It does not exist until you write it.** Until then the client shows a built-in
  starter Home — name, model, skills, tools, trust, address — rendered fresh each
  time, so it follows the agent as skills come and go. Writing the file replaces
  that for good: from then on it is yours, nothing regenerates it, and a skill you
  add later will not appear until you add its button.
- Keep it under 2MB — the host won't send a larger file, and the Home pane goes blank. Inline images are base64, which is ~33% bigger than the source file, so compress screenshots before embedding them.
- Keep the responsive layout and `prefers-color-scheme` dark mode intact.
- **A media query here measures the Home pane, not the browser window.** The page renders inside its own iframe, so `@media (max-width: 560px)` means "when the pane is narrower than 560px" — the question you wanted to ask. No container queries needed. The pane is resizable, roughly 320–900px, so design for the narrow end: a four-column table needs about 500px, and below that the column the table exists for ends up off the right edge behind a scrollbar. Give wide tables a stacked form for narrow panes.
- Do not add `<script>` tags or inline `onclick` handlers — OChat strips all scripting. Interactivity comes from the declared tags (`data-ochat-skill`, `<co-filter>`, `<co-table>`), which the client renders for you.
- Keep styles inline in the file (external URLs are blocked in the sandbox).
- **No links out.** A Home page is one self-contained page. Don't add `<a href="https://…">` — the client cancels those clicks, so the link renders as dead text. Same-page anchors (`href="#section"`) work fine. If you want the user to *do* something, that's what a `data-ochat-skill` button is for.
