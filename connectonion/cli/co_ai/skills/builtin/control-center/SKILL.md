---
name: control-center
title: Update the Control Center
description: Update the agent's Control Center. Use for "update my Control Center", "redesign my Control Center", or "/control-center". The old /dashboard command is a compatibility alias.
---

# Control Center Skill

The agent's Control Center can be customized through `.co/control-center.html`, beside `.co/skills/`. Read that first, then `.co/dashboard.html`, then the root `dashboard.html`: the first existing file wins. Edit the existing file where it is; new snapshots use `.co/control-center.html`. O Chat renders it in a sandboxed iframe beside the chat and re-reads it after every run. You edit it with your normal file tools (Read, Edit, Write, Bash) — there is no special API.

## Instructions

1. **Read the file first** — `.co/control-center.html`, then the legacy `.co/dashboard.html` or root `dashboard.html` if that is where this agent's already is — so you preserve its structure and styles before changing anything.
2. **Make the smallest edit that satisfies the request** — change the data or add a section; don't rewrite the whole file unless the user asks for a redesign.
3. **Keep it visual, not textual.** Lead with identity, one focal Run box, and up to four useful shortcuts. Fold All skills (count and search), Recent, and Host details; the first screen must fit at 390×844. A Control Center is glanceable, not a document.
4. **Write the file** and stop. O Chat picks up the change automatically after the run.

## Skill action buttons

A button that runs something MUST be a real, user-invocable skill, wired like this:

```html
<button data-ochat-skill="daily-brief">Build today's brief</button>
```

- The `data-ochat-skill` value is the exact skill name; O Chat validates it and runs `/daily-brief` as a visible chat turn.
- Optional arguments: `data-ochat-skill="meeting-prep" data-ochat-args="2pm sync"` → runs `/meeting-prep 2pm sync`.
- Use an **outcome-oriented label** ("Prepare my next meeting"), not the raw skill name.
- Only reference skills that actually exist. Never invent skill names, and don't add buttons for internal/bootstrap skills.
- **Only project skills work as buttons** — the ones in `.co/skills/` or `.claude/skills/`. Your personal skills (`~/.co/skills/`) and builtin skills aren't published to clients, so a button for one renders but silently refuses to run. Check the skill's location before wiring it up.

## Filtering a long list

A Control Center pane that lists thirty skills is a wall. Declare the list filterable and
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

- One file: `.co/control-center.html` (legacy filenames remain readable). No sidecar JSON, no build step.
- **It does not exist until you write it.** Until then the client shows a built-in
  starter Control Center — identity, one Run box, up to four pinned skills (four
  prompt suggestions on day zero), and folded All skills, Recent, Host details — rendered fresh each
  time, so it follows the agent as skills come and go. Writing the file replaces
  that for good: from then on it is yours, nothing regenerates it, and a skill you
  add later will not appear until you add its button.
- HTML may use up to 128 MiB of UTF-8 bytes. The transport budget is 256 MiB including JSON escaping and encrypted/base64 overhead. Self-hosted relays must match that receive budget. Loading failures show an error inside Control Center; do not remove useful page content merely to fit the old 2 MiB cap.
- Inline the Fresh tokens from the bundled starter. Light is default; dark requires `data-theme="dark"` (or `"auto"`). Use soft green for identity, deep green for marks, and Fresh fill with dark ink only for Run.
- Call the surface **Control Center** (控制中心), including mobile labels. Use sentence case, system fonts, 44px touch targets and progressive disclosure.
- **A media query here measures the Control Center pane, not the browser window.** The page renders inside its own iframe. The pane is resizable, roughly 320–900px, so design for the narrow end: a four-column table needs about 500px, and below that the column the table exists for ends up off the right edge behind a scrollbar. Give wide tables a stacked form for narrow panes.
- Do not add `<script>` tags or inline `onclick` handlers — O Chat strips all scripting. Interactivity comes from the declared tags (`data-ochat-skill`, `<co-filter>`, `<co-table>`), which the client renders for you.
- Keep styles inline in the file (external URLs are blocked in the sandbox).
- **No links out.** A Control Center is one self-contained page. Don't add `<a href="https://…">` — the client cancels those clicks, so the link renders as dead text. Same-page anchors (`href="#section"`) work fine. If you want the user to *do* something, that's what a `data-ochat-skill` button is for.

## Prompt and copy declarations (O Chat follow-up required)

The Host snapshot contains no scripts. The redesigned starter declares:

```html
<form data-ochat-prompt>
  <label for="prompt">What should Maren do?</label>
  <textarea id="prompt" name="prompt" required maxlength="10000"></textarea>
  <button type="submit">Run</button>
</form>
<button data-ochat-prompt="Help me plan my day.">Plan my day</button>
<button data-ochat-copy="0xFULL_ADDRESS">Copy</button>
```

O Chat must intercept submit/click, trim the prompt and send it as a visible turn
in the current conversation using the same authorization and idle checks as Chat.
Ignore empty prompts; never navigate/submit the form. Copy must write the exact
attribute value and show Copied or a visible error. These new declarations require
client support; they do not execute in an older O Chat. Published skill buttons and
`co-filter` keep their existing contract. Do not claim the new controls work until
that client follow-up is shipped. Do not add scripts to work around the sandbox.
