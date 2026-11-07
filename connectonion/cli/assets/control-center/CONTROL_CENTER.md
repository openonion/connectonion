# Control Center app

This is a complete static Web app: HTML, CSS, JavaScript and local assets. Replace
it with the output of React, Vue, Svelte or another browser build if useful. Keep
all executable chunks in this directory so one revision covers every served byte.

The starter uses the browser entry point from `@connectonion/react`. `sdk.js` is a
vendored build of that entry point; `sdk-version.json` records its package and hash,
and `SDK_LICENSE.txt` carries its license. `control-center.js` owns the starter UI.
Do not invent a second bridge or open another Agent socket inside the iframe.

## Connect to the current Agent Chat

O Chat puts `co-parent` and `co-revision` in the URL fragment. Pass them to
`connectControlCenter`. The SDK verifies the parent origin, iframe window, revision
and fresh load epoch before accepting a private MessagePort. A bare static URL has
no Agent identity or conversation authority.

```js
import {connectControlCenter} from './sdk.js'
const parameters = new URLSearchParams(location.hash.slice(1))
const client = await connectControlCenter({
  parentOrigin: parameters.get('co-parent'),
  revision: parameters.get('co-revision'),
})
client.subscribe(snapshot => {
  // Normalized chatItems, skills, status, connectionState, sessionId, agentAddress.
  // Render text as text. snapshot.truncated reports bounded recent history.
})
await client.sendMessage('Explain the current invoice.')
await client.runSkill('generate-invoice', 'invoice 1042')
```

Both actions appear as attributable turns in the current Agent Chat. On the landing
page, the first action creates the Chat. Only an explicit
`{conversation: 'new'}` option creates another Chat. Requests are correlated and
bounded; `signal` and `timeoutMs` cancel only the still-pending action. A current-chat
action waits for the Agent result. A new-chat action acknowledges the handoff. An
Agent already working refuses another app action. Inspect Chat before retrying an
uncertain action. Closing or reloading the iframe cancels its pending requests.

## Review and activation

Configure `control_center` in the Host's `.co/host.yaml` with `app_id`, `build` and an
operator-provided `serving_domain`. The serving domain must use a different
registrable domain from O Chat, Agent endpoints and identity services. The static
service is deployed separately from the authenticated upload API.

An administrator can use **Update app** or ask the Agent to edit this directory and
call `update_control_center`. The runtime captures the exact immutable bundle,
executes the packaged `control-center-review` skill in a fresh reviewer process,
checks that the build did not change, uploads frozen bytes, then records approval
outside the authored project. Never write an `approved` descriptor yourself.

Every revision gets an isolated immutable HTTPS origin:

```text
https://r-<account-app-revision-hash>.<isolated-serving-domain>/index.html
```

A rejected or failed update keeps the previous approved app active. O Chat shows
findings, Code/Preview, retained source/diffs, history, rollback and **Fix with AI**.
Rollback requires retained approval under the current review policy and an available
artifact. Approval describes the automated review; it is not proof that an app is
free of defects.

Automatic updates are disabled by default. Configure an interval or a daily time
and timezone, plus optional internal turn/skill/source-change triggers. The Host
coalesces events, excludes its own generated turns, permits one writer and applies
daily attempt and reported-cost budgets. Interrupted updates require manual retry.
This feature does not schedule mail or external provider messages.

## Browser behavior

The app has normal per-origin storage, fetch/XHR, WebSocket/SSE, workers, canvas,
SVG, WebGL and WebAssembly. Bundle executable code locally: the serving CSP blocks
external scripts and string evaluation. Permissions such as camera, microphone,
clipboard, geolocation and fullscreen must be declared in the reviewed capabilities
and still require browser/user grants. Do not put credentials in the public bundle.

For a visual preview, serve this directory with a static server. It has no Agent
authority until opened in an approved O Chat session. Focus/fullscreen preserve the
existing iframe; **New tab** opens an O Chat session shell that restores Host state.

## First screen and identity

Use the name Control Center (控制中心) everywhere, including phone navigation.
The first screen uses inline `chat-ui/tokens.css` v1 Fresh tokens, light by default;
set `data-theme="dark"` or `"auto"` on the root to opt into dark mode. It contains
one Run box, four pinned published skills (alphabetical shortcuts), or four prompt
suggestions when none are published, then folded All skills, Recent and Host details.
Do not add a second composer. All actions use the existing SDK connection.

The question "What should {name} do?" is the page's headline and the Run box's label,
so the agent's name appears once. Pinned items are a quiet list, not cards. Keep the
standard's scale: sizes 12/13/14/16/20/24, weights 400/600/700, radius 8 for buttons
and inputs, 12 for cards, one Fresh fill (Run) per region, 44px touch targets and one
column under 400px. While a run is in flight the form carries `data-ochat-state="running"`
and folds into a single "● Running" row showing the task; it unfolds when the agent is
idle again. That is the page's one motion (180ms), and it is off under
`prefers-reduced-motion`. Its "Open in Chat" button posts
`{type: 'connectonion.control-center/open-chat'}` to the parent origin.
Skills read as their `title` (else the slug in sentence case); All skills adds `/slug`.
New-agent suggestions live in `suggestions.json`, which the Host's starter page also reads.

Presence maps `connected` to Online, `reconnecting` to Connecting… and `disconnected`
to Offline. Task state remains separate. Buttons are disabled while offline/busy.
The copy button copies the full address; Host details retains selectable full text.
The current bridge supplies `agentAddress` but does not guarantee an agent name;
this starter reads optional `agentName`, falling back to Agent. O Chat/SDK should
supply the profile name and pass its theme to finish identity/theme integration.
The snapshot's declarative `data-ochat-prompt`/`data-ochat-copy` contract is described
in `docs/network/control-center.md`; this app uses `sendMessage` and the Clipboard
API instead. Clipboard permission may need declaring for the approved iframe.
