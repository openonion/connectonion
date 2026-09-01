# A button should become a conversation turn

*2026-09-01 · Design Journal*

The invoice was the useful test. A Control Center can show a polished invoice,
but the moment someone clicks “Generate invoice,” the product has to decide what
that click means. If it starts a hidden task, Chat cannot explain what happened.
If it always opens a new conversation, the next question loses the invoice's
context. If the website opens its own Agent socket, two clients begin competing
to define one session.

The old Dashboard avoided most of that ambiguity by avoiding JavaScript. Its
buttons were data attributes on a locked-down HTML snapshot. The client translated
one attribute into a visible `/skill` message. That boundary was safe and clear,
but it could not become a complete website with routes, modules, storage, assets,
or a modern framework runtime.

The full Web Control Center keeps the important part of the old behavior. O Chat
owns the authenticated Agent connection. It transfers a narrow `MessagePort` to
the reviewed website, and the website may request `send_message` or `run_skill`.
Both requests become ordinary, attributable user turns in the current Chat. On a
landing page, the first request creates that Chat. A new Chat appears only when
the app explicitly asks for `conversation: "new"`.

That decision changed what the default template needed to be. A static example
with one hard-coded invoice button would demonstrate the bridge while failing
every real Agent. The parent therefore sends the authenticated published skill
list as initial context. The template renders one button per skill and keeps a
normal message form beside it. Future templates can change their presentation
without inventing a second capability-discovery path.

There was another tempting shortcut: let the project write an “approved” app
descriptor that points at localhost or any HTTPS page. That would make the iframe
appear immediately, but it would also let the author claim that its own code had
passed independent review. We did not cross that boundary. `co create` and
`co init` now produce the editable website source, but the legacy snapshot remains
the active fallback until immutable upload, content addressing, and independent
review can produce an authenticated `CONTROL_CENTER_APP.app.url`.

The URL distinction is deliberately visible in the docs. The E2E fixture uses
`https://control-center.e2e.test/invoices/`; it is a fake address that Playwright
intercepts. The production shape is content-addressed:
`https://apps.openonion.ai/<agent-address>/<sha256-revision>/index.html`. The iframe
uses the descriptor URL exactly, rather than reconstructing or guessing it.

We measured the behavior at both boundaries. The O Chat browser test clicked the
invoice skill, observed one visible `/generate-invoice invoice 1042` turn, sent a
follow-up into the same session, and opened another Chat only for the explicit-new
case. The bundled template was rendered at 1280 pixels and 375 pixels; it kept
44-pixel controls, stacked on the phone, and produced no horizontal overflow. The
installed wheel was also inspected to confirm that all three template files ship,
because a source-tree test cannot prove that package data reached PyPI.

The lesson is that a website button is not merely a callback. In an Agent product,
it is a claim about identity, conversation ownership, attribution, and context.
Making that claim visible in Chat gives the richer website the same understandable
semantics the small Dashboard got right.
