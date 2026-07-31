# Dashboard — your agent's Home page

Every hosted agent can have a **Home page**: a single file, `dashboard.html`, in the
project root. A chat client renders it beside the conversation, so opening your agent
shows something useful before you type anything.

```
my-agent/
├── agent.py
├── dashboard.html      ← the Home page
└── .co/
```

The browser can't read a file inside your agent's container, so the Host reads
`dashboard.html` and sends it over the WebSocket the client is already authenticated
on. There's no extra endpoint, no build step, and no sidecar JSON.

## It starts working on its own

The first time you run `host()`, if there's no `dashboard.html`, ConnectOnion writes a
starter one: your agent's name, what it runs on, and **every** skill it publishes as a
one-click button with its description underneath.

```python
from connectonion import Agent
from connectonion.network import host

host(lambda: Agent("lisa", tools=[...]))
# → Created dashboard.html — your agent's Home page.
```

After that the file is yours. ConnectOnion never overwrites it.

### Where it lives, and why there

`dashboard.html` sits at the **project root**, next to `agent.py`. Not in `.co/`, and
that is not cosmetic:

- `co deploy --to` rsyncs the project tree **excluding `.co/`**. A dashboard under
  `.co/` would silently not travel, and the deployed agent would look like it had no
  Home.
- The template Dockerfile does `COPY . .`, so the root is in the image.
- The `.gitignore` `co create` writes does not ignore it, so it gets committed — a
  dashboard you edited is part of your agent, like its prompt.

**`co create` and `co init` deliberately do not scaffold one.** At create time the
project has no skills yet, and `ensure_dashboard` never overwrites an existing file —
scaffolding then would freeze an empty Home forever. It is written on the first
`host()`, which is the first moment the agent's skills are actually known.

On a deployed agent the same rule applies on the server: `host()` writes a starter
there if the rsync carried none. That means an agent deployed without a dashboard gets
one built from the skills that actually made it onto the server, which is the honest
answer rather than a copy of what your laptop had.

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
open it in a browser and you see what a starter dashboard looks like — followed by a
`<!--FRAGMENTS` marker and the repeated pieces (a skill row, a group, a flat list, the
empty state) as `<template>` tags. Python splits on the marker, fills in the
placeholders, and contains no HTML of its own. Everything below the marker, including
its notes, is stripped before anything is written.

Edit that file to change how a starter dashboard looks.

Anything you write there has to survive the client's contract: **no JavaScript** (the
CSP runs only the client's own bridge script, so an agent's script tag or inline
handler never executes), images only as `data:` URIs, and no links out. The starter is
CSS-only for exactly that reason — the disclosure groups are `<details>`/`<summary>`,
which is the one thing that works without scripting.

## Editing it

`dashboard.html` is a plain HTML file — edit it with any editor. Or ask the agent: the
built-in `dashboard` skill teaches it the file's contract.

```
/dashboard put this week's numbers on my home page
```

Write plain HTML and inline CSS. Two constraints, both enforced by the client's
sandbox rather than by convention:

- **No scripting.** `<script>` tags and inline `onclick` handlers are stripped by a
  Content-Security-Policy. Action buttons (below) are the only way to make something
  happen.
- **No external URLs.** No CDN stylesheets, no remote images, no fonts from the
  network. Inline your styles and use `data:` URIs for images.
- **No links out.** A Home page is one self-contained page. A client cancels clicks
  on `<a href="https://…">`, so such a link renders as dead text — use a
  `data-ochat-skill` button when you want the user to *do* something. Same-page
  anchors (`href="#section"`) work normally.

Keep it under **2MB**. The Host won't send a larger file, and the Home pane goes
blank. Inline images are base64, which is ~33% larger than the source file — compress
screenshots before embedding them.

> **Why so locked down?** The client renders your `dashboard.html` in a sandboxed
> iframe with a strict Content-Security-Policy, because from its side the file is
> untrusted, agent-authored HTML. Everything above follows from that: nothing loads
> from the network, nothing scripts, and nothing navigates away. A Home page is a
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
| On connect, right after `CONNECTED` | Home paints before the first message |
| After each run, right after `OUTPUT` | A run that rewrote the dashboard shows the new version |

The post-run send is skipped when the file hasn't changed since that connection last
saw it, so an unchanged Home costs nothing per turn. Nothing is polled and nothing
watches the filesystem — if you edit `dashboard.html` by hand while a client is
connected, the change shows up after the next run.

An agent with no `dashboard.html` sends nothing, and clients simply show no Home pane.

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
| `ensure_dashboard(agent_metadata, project_dir=None)` | Write the starter if absent, and anchor the directory later reads resolve against |
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
