# The Beta Caught the Wrong Question

The fifth 1.7 beta had passed its artifact checks. The next change looked small:
give every tool call a human-readable line so a person could follow an agent
without opening raw arguments.

Our first contract named that line `reason`. It worked mechanically. The model
filled the field, Core transported it, and the React client could read it. Then
we put the result in the conversation UI.

A simple system check no longer looked simple. Above `uname -a`, the agent wrote
that it needed to inspect the operating system because the user had asked about
release readiness. The interface repeated the prompt, claimed to know the
agent's motivation, and used more space explaining the call than reporting its
result. The field had answered exactly the question we asked. We had asked the
wrong question.

That was the moment the beta earned its name. Compatibility tests could prove
that a string survived the wire, but only the end-to-end reader showed that the
string did not belong in the product.

For Beta 6, the field is `summary`: a short action phrase such as “Check the
operating system.” The public React beta learned to preserve it first. O Chat
then moved the action beside a status dot and quiet duration, with the tool name,
arguments, and result folded underneath. Only after that reader reached
production did Core begin writing summaries into live and replayed traces.

Older calls still execute without the field. Ordinary functions never receive
the presentation value as a surprise argument, while a function that genuinely
declares its own `summary` parameter keeps it. Those details matter, but they are
not the lesson of the beta.

The lesson is that a contract can be type-correct and still ask the product to
lie. Beta 6 changes the question from “Why did you do this?” to the one the
interface can answer honestly: “What are you doing?”
