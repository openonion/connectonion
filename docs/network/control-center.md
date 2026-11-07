# Full Web Control Center

A Control Center is a complete static app beside Chat. HTML, CSS, JavaScript,
framework chunks and assets travel as one immutable revision. The 1.8.4 candidate
coordinates Core, the React SDK, O Chat and a separate static hosting service.
Deploying that service and its wildcard TLS domain is an operator step; the CLI
does not invent a working production URL.

## Start and configure

`co create` copies `.co/control-center/` once. It contains `index.html`,
`control-center.js`, the browser SDK `sdk.js` with its version/hash and license,
and `CONTROL_CENTER.md`. The directory belongs to the author and is never overwritten
by later initialization. Default `co init` initializes global credentials only.

The starter includes Agent identity, a message form, published skill actions,
Diagnostics and a live Recent Chat view. It uses the same browser SDK as framework
apps. A plain static-server preview renders the document but has no Agent authority.

Add this configuration to the Host's `.co/host.yaml` after provisioning the hosting
API and a wildcard domain on a separate registrable domain from O Chat and identity
services. The names below are placeholders, not available production endpoints.

```yaml
control_center:
  app_id: home
  build: .co/control-center
  entry: index.html
  serving_domain: control-apps.example.net
  capabilities: [clipboard-write, fullscreen]
  updates:
    enabled: false
    every_seconds: 3600
    tz: UTC
    events: []
```

The upload API follows the shared backend resolver and ambient credentials;
`api_url` can explicitly select another HTTPS API. Runtime state defaults to the
global config directory under `runtime/control-centers/`. It must remain outside
the authored project and outside the author tools' filesystem authority. This is
not an operating-system sandbox for an Agent with unrestricted native tools.

## Review, activation and rollback

An administrator chooses **Update app**, or asks the Agent to edit the build and
call `update_control_center`. All update paths share the same operation:

1. Capture every regular build file and derive a canonical manifest/revision.
2. Run the packaged `control-center-review` skill in a fresh reviewer process.
3. Check that the source still matches, upload frozen bytes, then check again.
4. Record approval and activate only the reviewed revision on its HTTPS origin.

Each account/app/revision receives its own origin, shaped like
`https://r-<hash>.control-apps.example.net/index.html`. The authenticated upload API
and public static ASGI app are separate services. No identity cookies or API routes
belong on the serving origin. Bundle limits are 256 files, 8 MiB per file and 20 MiB
total; executable review source is limited to 512 KiB. Production framework bundles
must fit these bounds and the serving CSP.

Review runs once with no author tools/history, a 90-second process deadline and
4,096 output-token bound. The default follows Core's current default model;
`review_model` explicitly overrides it. Runtime-owned provenance binds model,
execution, policy, time, cost and findings to the revision. A reported review cost
above $0.25 blocks activation. These guards cannot undo provider charges.

A blocked, failed or changed build keeps the previous approved app visible. O Chat
shows findings, **Fix with AI**, Code/Preview, retained source/diffs and revision
history. Rollback requires retained approval under the current policy and a reachable
artifact. Historical source is checked against its reviewed size/hash before display.
The private history retains up to 100 attempts within 4 MiB while preserving the
active approval and newest attempt. Source and diff displays are separately bounded.

## Conversation and browser behavior

The iframe connects through a verified window/origin/revision handshake and fresh
load epoch. Its private MessagePort carries ordered normalized ChatItems, connection
state, skills and current session. Gaps request a fresh snapshot. The parent bounds
recent history and reports truncation. The iframe never opens an Agent socket or
receives identity keys.

`sendMessage` and `runSkill` create visibly attributed conversation turns. Current
conversation is the default; the landing page promotes its draft on the first action.
Only `conversation: 'new'` creates another Chat. Current-chat app actions must start
while the Agent is idle and await completion; cancellation reaches only their pending
turn. New-chat actions acknowledge the handoff. After a timeout, inspect Chat before
retrying an uncertain action.

Focus and fullscreen preserve the iframe. **New tab** opens an O Chat session shell,
which restores the same conversation and connects its approved revision. A pinned
revision mismatch is explicit. Reload creates a fresh port; stale ports cannot act.

The app has native per-origin storage, fetch/XHR, WebSocket/SSE, workers, canvas,
SVG, WebGL and WASM. The serving CSP allows bundled code and normal data APIs while
blocking external scripts and string evaluation. Declared camera/microphone/location/
clipboard/fullscreen capabilities become iframe permissions and still require browser
grants. Public assets must never contain credentials.

## Automatic updates

Updates are disabled by default. Configure an interval of 60–604800 seconds or a
daily HH:MM with IANA timezone, and optionally completed Agent turns, explicit skill
turns or source-change events. The existing Host minute scheduler applies the same
rules through direct, Relay-only and local Host configurations.

Events deduplicate for seven days (up to 1,024 IDs), coalesce and debounce up to five
minutes. The updater excludes its own turns and already-active source. A durable
claim and OS locks allow one writer; downtime produces one due update rather than
a replay burst. An interrupted process remains paused until manual retry. Ordinary
failures wait for the next configured occurrence or manual action.

Defaults allow 24 attempts/day (configurable 1–96) and $2 reported daily cost. Author
turns have eight iterations and a five-minute/$0.50 between-call guard; an in-flight
provider call can finish after the guard. Settings/status expose last attempt,
success, error, next run and revision. This does not schedule mail or provider messages.

See [candidate acceptance](../acceptance/1.8.4-control-center.md),
[DD071](../design-decisions/071-control-center-revisions-and-runtime-approval.md), and
[the snapshot contract](#host-snapshot).

## Host snapshot

Before an approved app is available, the Host sends a self-contained Control Center
snapshot. It shows identity and Online presence, one **What should {name} do?** Run
box, up to four published skills, and folded **All skills** (count and search),
**Recent**, and **Host details**. With no published skills, four explicitly labelled
prompt suggestions appear instead. The full address is selectable in Host details;
the identity row shows a short address and Copy.

The first existing file wins, without moving or overwriting anything:

1. `.co/control-center.html` — preferred name for new custom snapshots.
2. `.co/dashboard.html` — compatibility alias.
3. `dashboard.html` in the project root — older compatibility location.
4. No custom file — the bundled `starter.html`, freshly rendered from Host metadata.

`co create`/`co init` scaffold the app directory `.co/control-center/`; they do not
freeze a snapshot file. The directory and `.co/control-center.html` are distinct.
`co deploy --to` carries project-authored snapshot files along with skills.

Ask `/control-center` to customize the snapshot. `/dashboard` remains a skill alias.
Write inline CSS, no scripts or inline event handlers, no remote assets or external
navigation. Inline the tokens from `chat-ui/tokens.css` v1: Fresh green with dark
ink for Run, soft green identity, deep green marks, sentence case, system fonts,
44px touch targets. Light is default; `data-theme="dark"` enables dark mode and
`data-theme="auto"` opts into the OS setting. O Chat must pass its theme explicitly.

Published project skills use the existing client bridge:

```html
<button data-ochat-skill="daily-brief" data-ochat-args="today">Daily brief</button>
<co-filter target="#skills" placeholder="Search skills"></co-filter>
<div id="skills"><!-- direct children are searchable skill rows --></div>
```

Only skills published from `.co/skills/` or `.claude/skills/` qualify. User and builtin
skills are not published. The client validates each skill and creates a visible turn.

The redesigned snapshot also declares the following **new client contract**:

```html
<form data-ochat-prompt>
  <label for="prompt">What should Maren do?</label>
  <textarea id="prompt" name="prompt" required maxlength="10000"></textarea>
  <button type="submit">Run</button>
</form>
<button data-ochat-prompt="Help me plan my day.">Plan my day</button>
<button data-ochat-copy="0xFULL_ADDRESS">Copy</button>
```

O Chat must cancel native submission, trim/validate the prompt (nonempty, at most
10,000 characters), and dispatch it through the current conversation's normal
message path with authorization and idle checks. While that turn runs, O Chat sets
`data-ochat-state="running"` on the form and writes the task into the form's
`[data-ochat-task]` element as text: the submitted prompt, or the clicked button's
`.name` (the skill or suggestion title) when a pinned item started it. The bundled
snapshot's own CSS folds the box into that one "● Running" row and greys the pins.
The next `DASHBOARD_SNAPSHOT` replaces the document, so the state is gone and the run
appears in Now instead: O Chat must not re-apply it to the new snapshot, or the run
would show twice. The snapshot never sets the state itself, because it cannot know
live state.

Runs waiting on someone (running, needs approval, needs input, needs sign-in) are
rendered in an open **Now** section above the pinned skills, and left out of Recent.
Each Now row, and the folded Running row, carries
`<button data-ochat-open="chat">Open in Chat</button>`; O Chat switches to the Chat tab
when it is pressed. The scaffolded app asks for the same thing by posting
`{type: 'connectonion.control-center/open-chat'}` to its parent origin.

Skills show their SKILL.md `title:` (else the slug in sentence case: `post-to-x` reads
"Post to X"). The slug stays in `data-ochat-skill`, and All skills also shows it as
`/post-to-x`, so the filter matches title, slug and description. Prompt suggestions send their
attribute value through that same path. Copy uses the exact value and reports
success/failure. These declarations require an O Chat change; older clients do not
honour them. Snapshot scripts cannot implement this themselves. The scaffolded app
already runs prompts through `client.sendMessage` and skills through `runSkill`.

The snapshot's Recent history is scoped to the socket's verified address, including
admins. Schedules are visible only to admins. Custom files are served as written to
every client; keep private content out of them. A snapshot is historical and does
not subscribe to live task events; the app bridge does.

`DASHBOARD_SNAPSHOT` is unchanged. It carries `html` and optional `session_id` on
connect and after runs; unchanged custom files are not resent. UTF-8 HTML is capped
at 128 MiB and the encoded transport envelope at 256 MiB. Load failures render an
explanatory Control Center. Internal Python names (`dashboard_path`,
`read_dashboard_snapshot`, `send_dashboard`, `ensure_dashboard`) remain compatible.
See [websocket-protocol.md](websocket-protocol.md).
