# An Action Is Not a Reason

A tool implementation knows what its function does. A model can also supply a
short description of the concrete action it is taking. Neither fact gives a
reader permission to claim why that action was chosen.

The first draft of the 1.7 tool contract called its presentation field
`reason`. That name made a simple activity line carry too much meaning. It
encouraged explanations, squeezed longer prose into the transcript, and risked
turning a model's guess about motivation into a statement of fact.

The contract now asks for a short `summary` instead: an action phrase such as
“Check the operating system” or “Search the order table.” Core carries it beside
the executable arguments in both the live start event and the durable result
trace. Readers show it as the primary activity line while keeping tool names,
arguments, and raw output available on demand.

The field is required in schemas presented to current models, but optional on
the wire. That distinction preserves replay and third-party compatibility. An
old call without a summary still executes; its reader derives a deterministic
action label from the tool name and does not invent intent.

Presentation metadata is removed before an ordinary function runs. If a tool
already owns a real `summary` parameter, tool creation marks that collision and
the executor preserves it. In both cases the trace receives the same
whitespace-normalised, bounded phrase.

The distinction keeps the interface honest: show what is happening, expose the
details when requested, and leave “why” to the surrounding conversation.
