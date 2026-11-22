# Control Center page

> New projects also receive a full Web app in `.co/control-center/`. It can use
> JavaScript, routes, external assets, and the typed Chat bridge after it has been
> uploaded and independently reviewed. See [control-center.md](control-center.md).

Every hosted agent has a **Control Center** beside the conversation. When the agent
has not written its own page, the Host renders the starter, top to bottom:

1. **Header**: the agent's initial, name, the `summary:` from `.co/host.yaml`, and one
   quiet line: `5 skills · 4 people · model` (the people count is shown to admins only).
2. **Status**: the agent's own live numbers from `.co/status.json`, when it writes one
   (see below).
3. **Skills**: every published skill as a tile; one tap starts a chat with it.
4. **People** (admins only): everyone admitted, with a name when one is known, a role
   badge (`admin`, `whitelist`, `contact`), a short address `0x48a0…fbee`, how many turns
   they ran and when they were last seen, Remove / Block, and the invite code with
   New code / Turn off.
5. **Recent**: the viewer's own last five runs, with the prompt, status and duration.
6. **Health**: one line (model · version · relay · trust; admins also see uptime and
   the last failure), then the agent's full address.

People and Recent sit side by side from 900px wide; below that everything is one column.
A custom page is the single file `.co/control_center.html`.

**Each client sees its own activity.** The starter's "Recent" list is rendered
for the connecting client's verified address: it shows the runs that address
started and nobody else's, **admins included** (#696: the prompt text is verbatim).
An admin sees everyone's activity as counts and times on the People rows, never
their prompts. The "Scheduled" section is operator configuration and is shown only
to an admin. A custom `.co/control_center.html` is served as written to every
client, so do not put anything in it that a visitor should not read.

**Where People names come from.** The name the operator saved for that address with
`co handoff` (`~/.co/handoff/contacts.json` on the Host). Trust lists hold bare
addresses and a connecting client sends no profile name, so anyone else is shown by
short address.

## Status: `.co/status.json`

An agent that has something to report right now (a queue, a count, what is overdue)
writes `.co/status.json`, and the starter shows it first, above Skills, to every
admitted viewer:

```json
{
  "title": "Front desk now",
  "updated_at": "2026-11-22T19:42:48+11:00",
  "metrics": [
    {"label": "Open requests", "value": 23},
    {"label": "Overdue", "value": 6, "tone": "bad"},
    {"label": "Awaiting reply", "value": 2, "tone": "warn"}
  ],
  "lists": [
    {"title": "Most overdue", "items": [
      {"text": "#2041 Hot water out in unit 7", "meta": "Harbour Dental · due 18 Nov", "tone": "bad"}
    ]}
  ]
}
```

- `metrics` render as a row of big numbers; `lists` as compact lists, text on the left
  and `meta` on the right.
- `tone` is `good`, `warn` or `bad`, or absent. Anything else is ignored.
- `updated_at` (ISO 8601) is shown as "updated 4m ago".
- `href` is accepted and ignored: the sandbox cancels links out, so a link would be
  dead text that looks clickable.
- Every string is escaped; the file cannot inject markup.
- No file, no block. A file that is not valid JSON, or not an object, shows one quiet
  line naming the problem; the rest of the page renders as usual.
- A run that rewrites `status.json` re-sends the page after that run, the same as a
  run that rewrites `control_center.html`. Nothing polls it: write it from the agent's
  turns or a `.co/schedule.yaml` entry.

The HTML snapshot is not the source of truth for a running task. It does not receive
thinking, approval, input-wait, Stop, failure, or completion frames. The client owns
that live status and renders it outside the sandboxed page, while the starter directs
the reader back to Chat for the current task, approvals, and results. A custom
Control Center should not hard-code runtime claims such as “Ready” or “Working”.

```
my-agent/
├── agent.py
└── .co/
    ├── control_center.html   ← optional custom Control Center
    └── skills/          ← and the skills it offers
```

The browser can't read a file inside your agent's container, so the Host reads
`control_center.html` and sends it over the WebSocket the client is already authenticated
on. There's no extra endpoint, no build step, and no sidecar JSON.

## It starts working on its own

When there is no `control_center.html`, ConnectOnion renders the bundled starter fresh.
It writes no file, so improvements and newly published skills appear after upgrades.

```python
from connectonion import Agent
from connectonion.network import host

host(lambda: Agent("maren", tools=[...]))
# → The client receives Maren's current Control Center.
```

If you create `.co/control_center.html`, the file is yours and ConnectOnion never overwrites it.

### Where it lives, and how it's found

`.co/control_center.html`, beside `.co/skills/`. Both are **what the agent is**, as opposed
to the logs and evals it accumulates — and that distinction is what `.co/` is sorted
by, not "config vs content".

The project is located by walking up for a `.co/` directory, the same way skills are
found. So it doesn't matter which directory you start the agent from:

```
my-agent/           ← found, because .co/ is here
├── .co/control_center.html
└── src/
    └── run.py      ← `python run.py` from here still serves the same Control Center
```

With no `.co/` above you, the custom-file lookup starts where the agent was started.

**Older names still work.** Before 1.9.7rc15 the page was called `dashboard.html`, and
before that it lived in the project root. The Host looks for, in order:

1. `.co/control_center.html`
2. `.co/dashboard.html`
3. `dashboard.html` in the project root

The first one that exists is served, and nothing moves, copies, or overwrites it — an
agent whose Control Center vanished on upgrade would be a worse bug than an
inconsistent name. When an old name is the one being served, `co host` prints one
line at startup suggesting the rename:

```
Control Center: rename /srv/maren/.co/dashboard.html to .co/control_center.html
```

#### It travels

`co deploy --to` protects server-owned `.co/` state such as identity, logs and evals,
while syncing project-authored files such as `.co/host.yaml`, `.co/skills/` and
`.co/control_center.html`. A deploy that dropped a custom Control Center would silently
replace it with the starter, so the page travels as ordinary project content.

#### The page isn't scaffolded

`co create` and `co init` do not write `.co/control_center.html`. At create time the project
has no skills yet, and writing the page would freeze an empty Control Center.
Instead the Host renders it from the skills and activity present on that server.

They do scaffold `.co/control-center/`, the source for the new full website. The two
surfaces coexist during migration: the page remains the fallback until the
full website has an approved, immutable `CONTROL_CENTER_APP.app.url`.

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

A dozen skills or fewer are shown as tiles, all of them. Past that the first eight are
shown, the rest sit behind one "N more skills" control, and a search box appears above
them. The list is alphabetical, so families such as `lark-base` and `lark-doc` land
together without a header.

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

`.co/control_center.html` is a plain HTML file — edit it with any editor. Or ask the
agent: the built-in `control-center` skill teaches the contract.

```
/control-center put this week's numbers in my Control Center
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

The Host accepts HTML files up to **128 MiB** (UTF-8 bytes). Files that cannot
be loaded show an explanatory Control Center page instead of hiding the pane.
The WebSocket transport budget is **256 MiB**, including JSON escaping and sealed
base64 overhead; unusually escape-heavy content can hit that budget first.
Self-hosted relays must set Uvicorn `--ws-max-size 268435456`. Older Python
clients must upgrade to receive snapshots beyond their previous default limit.
The snapshot protocol and the client sandbox are unchanged; this patch does not
enable JavaScript or external resource loading.

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

This matters because the pane is **resizable**: one page has to hold up anywhere
from 320px to 900px, not at the two or three widths a client used to pick. Design for
the narrow end first. A four-column table needs roughly 500px, so below that give it a
stacked form — otherwise the column the table exists for ends up off the right edge
behind a horizontal scrollbar, which nobody scrolls to find a number they came for.

> **Why so locked down?** The client renders your `control_center.html` in a sandboxed
> iframe with a strict Content-Security-Policy, because from its side the file is
> untrusted, agent-authored HTML. Everything above follows from that: nothing loads
> from the network, nothing scripts, and nothing navigates away. A Control Center is a
> glanceable, self-contained page whose one action is running a skill.
>
> Supporting external links later is a deliberate change to that contract, not a
> setting — it means deciding what a Control Center may navigate to and how (in-sandbox,
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
refuses to run. The starter page follows this rule automatically; if you hand-write
a button, check the skill's location first.

The client validates every button name against the skills your agent published, so a
button can only ever start a skill you actually have.

## When it updates

The Host sends the file at two moments:

| When | Why |
|------|-----|
| On connect, right after `CONNECTED` | Control Center paints before the first message |
| After each run, right after `OUTPUT` | A run that rewrote the page shows the new version |

The post-run send is skipped when the file hasn't changed since that connection last
saw it, so an unchanged Control Center costs nothing per turn. Nothing is polled and nothing
watches the filesystem — if you edit it by hand while a client is
connected, the change shows up after the next run.

An agent with no custom file receives the freshly rendered starter.

## Wire format

One frame, client-opaque to the relay:

```json
{
  "type": "CONTROL_CENTER_SNAPSHOT",
  "html": "<!DOCTYPE html>…",
  "session_id": "550e8400-…"
}
```

The Host also sends the same frame again as `DASHBOARD_SNAPSHOT`, its name before
1.9.7rc15. @connectonion/react still reads only that name, so the Host keeps sending it
until openonion/connectonion-react#116 ships and O Chat pins that release; dropping it
sooner would blank every Control Center. A client that reads both should treat them as
the same page.

See [websocket-protocol.md](websocket-protocol.md) for the full frame reference.

## Reference

`connectonion/network/host/ws_router/control_center.py`:

| Function | Purpose |
|----------|---------|
| `read_control_center_snapshot(session_id=None, *, viewer)` | Build the frame for `viewer` (`viewer_for(address, is_admin)`), or `None` if the file is missing, too large, unreadable, or not UTF-8 |
| `send_control_center_page(send_msg, session_id, conn, force=False)` | Send it, rendered for `conn`'s verified address, unless this connection already has the current file; reads off the event loop |
| `ensure_control_center(agent_metadata, project_dir=None)` | Anchor the project and metadata used to render the starter; writes no file |
| `project_root(start=None)` | Walk up for `.co/`; the project, not the cwd |
| `control_center_path()` | `.co/control_center.html`, or an older name if that is what exists |
| `render_starter(agent_metadata, viewer=EVERYONE)` | The day-zero HTML, from `starter.html`; `EVERYONE` is for in-process rendering only |
| `published_skills(skills)` | The project-tree skills a starter may offer as buttons |
| `MAX_CONTROL_CENTER_BYTES` | 128 MiB HTML cap; 256 MiB transport envelope |

The path is resolved against the project directory captured at host startup, not the
live working directory — so a tool that changes directories mid-run can't redirect
which file gets served.

## See also

- [host.md](host.md) — making an agent network-accessible
- [websocket-protocol.md](websocket-protocol.md) — the full protocol
- [../features/skills.md](../features/skills.md) — skills and their locations
