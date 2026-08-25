# Control Center

Every hosted agent has a **Control Center** beside the conversation. The Host renders
a current day-zero view—identity, quick actions, recent activity, searchable
capabilities, and diagnostics—before you type anything.
Custom pages keep the stable filename `.co/dashboard.html` for compatibility.

The HTML snapshot is not the source of truth for a running task. It does not receive
thinking, approval, input-wait, Stop, failure, or completion frames. The client owns
that live status and renders it outside the sandboxed page, while the starter directs
the reader back to Chat for the current task, approvals, and results. A custom
Control Center should not hard-code runtime claims such as “Ready” or “Working”.

```
my-agent/
├── agent.py
└── .co/
    ├── dashboard.html   ← optional custom Control Center (compatible filename)
    └── skills/          ← and the skills it offers
```

The browser can't read a file inside your agent's container, so the Host reads
`dashboard.html` and sends it over the WebSocket the client is already authenticated
on. There's no extra endpoint, no build step, and no sidecar JSON.

## It starts working on its own

When there is no `dashboard.html`, ConnectOnion renders the bundled starter fresh.
It writes no file, so improvements and newly published skills appear after upgrades.

```python
from connectonion import Agent
from connectonion.network import host

host(lambda: Agent("lisa", tools=[...]))
# → The client receives Lisa's current Control Center.
```

If you create `.co/dashboard.html`, the file is yours and ConnectOnion never overwrites it.

### Where it lives, and how it's found

`.co/dashboard.html`, beside `.co/skills/`. Both are **what the agent is**, as opposed
to the logs and evals it accumulates — and that distinction is what `.co/` is sorted
by, not "config vs content".

The project is located by walking up for a `.co/` directory, the same way skills are
found. So it doesn't matter which directory you start the agent from:

```
my-agent/           ← found, because .co/ is here
├── .co/dashboard.html
└── src/
    └── run.py      ← `python run.py` from here still serves the same Control Center
```

With no `.co/` above you, the custom-file lookup starts where the agent was started.

**An older `dashboard.html` in the project root still works.** If one is there it is
the file being served, and nothing moves, copies, or overwrites it — an agent whose
Control Center vanished on upgrade would be a worse bug than an inconsistent path. Move it to
`.co/` yourself when you feel like it. If both exist, `.co/` wins.

#### It travels

`co deploy --to` protects server-owned `.co/` state such as identity, logs and evals,
while syncing project-authored files such as `.co/host.yaml`, `.co/skills/` and
`.co/dashboard.html`. A deploy that dropped a custom Control Center would silently
replace it with the starter, so the page travels as ordinary project content.

#### It isn't scaffolded

`co create` and `co init` deliberately do not write one. At create time the project has
no skills yet, and the starter is never written over an existing file — scaffolding
then would freeze an empty Control Center forever. Instead the Host renders from the
skills and activity that are present on that server at read time.

### One starter for all your agents

Write `~/.co/starter.html` and every agent you host starts from that instead of the
bundled template.

It replaces the **template**, not the page: each agent still renders its own name and
its own skills. That matters — a client validates every button against the skills
*that* agent published, so serving one agent's finished Control Center for another gives a page
of buttons that silently do nothing.

An override only needs the parts you want to change. Its `<template>` fragments are
layered over the bundled ones, so restyling the page shell doesn't mean copying the
skill-row and group markup along with it.

### It scales with the agent

A dozen skills or fewer are listed flat — collapsing six items hides them behind a
click for nothing. Past that they're grouped by the family already in their names
(`lark-base`, `lark-doc`, `lark-sheets` → **lark**), with the count on each group and
the first one open. Names that share no prefix with two others land in **other**. A
115-skill agent is one screen you can scan instead of a list you have to scroll.

Skill names are shown verbatim, because that's what you type to run one — `/lark-base`,
not "Lark Base".

### Where the markup lives

One file: `connectonion/network/host/ws_router/starter.html`. It is a complete page —
open it in a browser and you see what the starter Control Center looks like — followed by a
`<!--FRAGMENTS` marker and the repeated pieces (a skill row, a group, a flat list, the
empty state) as `<template>` tags. Python splits on the marker, fills in the
placeholders, and contains no HTML of its own. Everything below the marker, including
its notes, is stripped before anything is written.

Edit that file to change how the starter Control Center looks.

Anything you write there has to survive the client's contract: **no JavaScript** (the
CSP runs only the client's own bridge script, so an agent's script tag or inline
handler never executes), images only as `data:` URIs, and no links out. The starter is
CSS-only for exactly that reason — the disclosure groups are `<details>`/`<summary>`,
which is the one thing that works without scripting.

## Editing it

`.co/dashboard.html` is a plain HTML file — edit it with any editor. Or ask the agent:
the built-in `dashboard` skill (name preserved for compatibility) teaches the contract.

```
/dashboard put this week's numbers in my Control Center
```

Write plain HTML and inline CSS. Two constraints, both enforced by the client's
sandbox rather than by convention:

- **No scripting.** `<script>` tags and inline `onclick` handlers are stripped by a
  Content-Security-Policy. Action buttons (below) are the only way to make something
  happen.
- **No external URLs.** No CDN stylesheets, no remote images, no fonts from the
  network. Inline your styles and use `data:` URIs for images.
- **No links out.** A Control Center is one self-contained page. A client cancels clicks
  on `<a href="https://…">`, so such a link renders as dead text — use a
  `data-ochat-skill` button when you want the user to *do* something. Same-page
  anchors (`href="#section"`) work normally.

Keep it under **2MB**. The Host won't send a larger file, and the Control Center pane goes
blank. Inline images are base64, which is ~33% larger than the source file — compress
screenshots before embedding them.

### A media query here measures the pane, not the window

The same sandbox that locks the page down also gives you something useful for free.
Your page renders inside its own iframe, and a media query inside an iframe evaluates
against **that frame's** viewport — so this means "when the Control Center pane is narrower than
560px", which is the question you actually wanted to ask:

```css
@media (max-width: 560px) { /* pane is narrow — stack the rows */ }
```

Measured, not assumed: with the pane at 320px the frame reports `innerWidth` 319 and
the query matches; dragged out to 900px it reports 899 and it does not. You do not
need container queries — the isolation already is one.

This matters because the pane is **resizable**: one dashboard has to hold up anywhere
from 320px to 900px, not at the two or three widths a client used to pick. Design for
the narrow end first. A four-column table needs roughly 500px, so below that give it a
stacked form — otherwise the column the table exists for ends up off the right edge
behind a horizontal scrollbar, which nobody scrolls to find a number they came for.

> **Why so locked down?** The client renders your `dashboard.html` in a sandboxed
> iframe with a strict Content-Security-Policy, because from its side the file is
> untrusted, agent-authored HTML. Everything above follows from that: nothing loads
> from the network, nothing scripts, and nothing navigates away. A Control Center is a
> glanceable, self-contained page whose one action is running a skill.
>
> Supporting external links later is a deliberate change to that contract, not a
> setting — it means deciding what a dashboard may navigate to and how (in-sandbox,
> where the destination still can't be trusted, or handed to a real browser tab).
> Until then, treat the page as a closed surface.

## Action buttons

A button that runs something declares the skill it runs:

```html
<button data-ochat-skill="daily-brief">Build today's brief</button>
```

Clicking it runs `/daily-brief` as a visible turn in the chat — the same as typing it.
Arguments are optional:

```html
<button data-ochat-skill="meeting-prep" data-ochat-args="2pm sync">
  Prepare my next meeting
</button>
```

**Only project skills work as buttons** — the ones in `.co/skills/` or
`.claude/skills/`. Your personal skills (`~/.co/skills/`) and ConnectOnion's builtin
skills aren't published to clients, so a button naming one renders but silently
refuses to run. The starter dashboard follows this rule automatically; if you hand-write
a button, check the skill's location first.

The client validates every button name against the skills your agent published, so a
button can only ever start a skill you actually have.

## When it updates

The Host sends the file at two moments:

| When | Why |
|------|-----|
| On connect, right after `CONNECTED` | Control Center paints before the first message |
| After each run, right after `OUTPUT` | A run that rewrote the dashboard shows the new version |

The post-run send is skipped when the file hasn't changed since that connection last
saw it, so an unchanged Control Center costs nothing per turn. Nothing is polled and nothing
watches the filesystem — if you edit it by hand while a client is
connected, the change shows up after the next run.

An agent with no custom file receives the freshly rendered starter.

## Wire format

One frame, client-opaque to the relay:

```json
{
  "type": "DASHBOARD_SNAPSHOT",
  "html": "<!DOCTYPE html>…",
  "session_id": "550e8400-…"
}
```

See [websocket-protocol.md](websocket-protocol.md) for the full frame reference.

## Reference

`connectonion/network/host/ws_router/dashboard.py`:

| Function | Purpose |
|----------|---------|
| `read_dashboard_snapshot(session_id=None)` | Build the frame, or `None` if the file is missing, too large, unreadable, or not UTF-8 |
| `send_dashboard(send_msg, session_id, conn=None)` | Send it unless this connection already has the current file; reads off the event loop |
| `ensure_dashboard(agent_metadata, project_dir=None)` | Anchor the project and metadata used to render the starter; writes no file |
| `project_root(start=None)` | Walk up for `.co/`; the project, not the cwd |
| `dashboard_path()` | `.co/dashboard.html`, or a legacy root one if that is what exists |
| `render_starter(agent_metadata)` | The day-zero HTML, from `starter.html` |
| `published_skills(skills)` | The project-tree skills a starter may offer as buttons |
| `group_skills(skills)` | `(families, loose)` split by name prefix, for long lists |
| `MAX_DASHBOARD_BYTES` | 2MB size cap |

The path is resolved against the project directory captured at host startup, not the
live working directory — so a tool that changes directories mid-run can't redirect
which file gets served.

## See also

- [host.md](host.md) — making an agent network-accessible
- [websocket-protocol.md](websocket-protocol.md) — the full protocol
- [../features/skills.md](../features/skills.md) — skills and their locations
