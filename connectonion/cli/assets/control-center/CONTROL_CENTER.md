# Control Center app

This directory is a complete Web app. It is intentionally ordinary HTML, CSS, and
JavaScript, so you can replace it with React, Vue, Svelte, Three.js, or another browser
stack without depending on O Chat's private component tree.

## What the default app does

- The message form calls `send_message`.
- Each published project skill becomes a `run_skill` button.
- Both actions become visible, attributable user turns in the current Agent Chat.
- On an Agent landing page, the first action creates that Chat.
- A separate Chat is created only when an app explicitly sends
  `conversation: "new"` in its action payload.
- The app receives a correlated acknowledgement. Agent replies currently appear in
  Chat; normalized output/event subscriptions are a later bridge capability.

## Files

- `index.html` — document and responsive styling.
- `control-center.js` — framework-neutral `MessageChannel` bridge client.
- `CONTROL_CENTER.md` — the maintenance contract future coding agents should read.

You can preview the document itself with any static server:

```bash
python -m http.server 4173 --directory .co/control-center
```

The preview has no Agent authority by itself. O Chat owns the authenticated Agent
connection and transfers a private `MessagePort` only after it loads an approved app
revision.

## The iframe URL

The iframe URL is not a local file path and not the Agent WebSocket URL. It is the
`url` in the authenticated `CONTROL_CENTER_APP` descriptor, normally shaped like:

```text
https://apps.openonion.ai/<agent-address>/<sha256-revision>/index.html
```

That URL must point to the exact immutable bundle that an independent reviewer
approved. The upload/review/activation command is not part of the current stable
package yet. Until it lands, keep editing this directory and use the legacy
`.co/dashboard.html` path in released clients; do not hand-author an `approved`
descriptor.

## Bridge requests

The parent transfers one port using a versioned `connect` message. Requests sent over
that port have this shape:

```js
port.postMessage({
  type: 'connectonion.control-center/request',
  version: 1,
  revision,
  id: crypto.randomUUID(),
  action: 'run_skill',
  payload: { skill: 'generate-invoice', args: 'invoice 1042' },
})
```

Use `action: 'send_message'` with `payload: { message }` for ordinary prompts. Omit
`payload.conversation` to continue the current Chat. Use `conversation: 'new'` only
for a workflow that truly needs isolated context.

Never request raw keys, tokens, or O Chat internals. Browser features such as camera,
microphone, clipboard, geolocation, or fullscreen must be declared in the reviewed
app descriptor so O Chat can build the iframe `allow` policy.
