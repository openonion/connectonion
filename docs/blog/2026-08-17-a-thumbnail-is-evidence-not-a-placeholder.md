# A Thumbnail Is Evidence, Not a Placeholder

The Work Room looked unfinished when a long Codex run had no picture. The
obvious response was to fill the empty space: reuse a command snippet, turn a
path into a label, or render a terminal-shaped card that looked like a live
screen. All three made the demo busier. None of them made it more truthful.

That distinction mattered once the run crossed several steps. The compact card
already knew the safe task title, current provider state, and latest semantic
activity. A made-up thumbnail would have implied a different fact: that the
browser had seen the provider's workspace. It had not. The provider protocol
had merely mentioned something that could be a file or a command, neither of
which is safe visual evidence.

The native adapters now take the narrower route. Codex can produce an artifact
only after its app-server reports a completed `imageView`, and only when the
path resolves to a regular PNG or JPEG inside the selected workspace. Claude
Code can produce one only from an explicit inline PNG or JPEG image block. Core
then validates byte signatures, size, provider identity, invocation, parent
tool call, and lifecycle revision before emitting a `provider_artifact` OIP
event.

The awkward part was what happened next. A screenshot might arrive while a
provider was running, while the next visible state was an approval or a
terminal result. Binding the image to the old revision made it disappear at the
moment a reader needed it most; leaving it unbound let an old screenshot look
like new state. We chose a small cache of one already-validated image per
invocation. Every newer lifecycle state re-emits that same image with its new,
correlated revision. A retry clears it first. The cache never stores provider
text, URLs, SVG, or arbitrary file paths.

This left the UI with a useful honest fallback. With an artifact, the card and
Work Room show a real current view. Without one, they show current semantic
progress, the latest completed evidence, and an intentionally hidden history.
The empty space is not a bug to disguise; it is the visible boundary between
what the provider did and what the interface can prove.

The tests exercise both sides of that boundary. They accept a completed
workspace PNG and a Claude inline PNG, keep it visible over later lifecycle
revisions, and reject an outside path, URL, SVG, malformed bytes, or stale
revision. The browser consumer still has to verify the published React package
and a real provider run before this becomes release evidence. Until then, the
correct thumbnail is the one the UI refuses to invent.
