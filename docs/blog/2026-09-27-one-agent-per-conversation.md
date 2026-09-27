# One agent per conversation

`host()` was designed to take a function. Each request calls it and gets a
new Agent built from scratch, so two conversations never share anything. That
was the rule since January.

In April, `host(agent)` was made to accept an instance too, to stop deployed
agents crashing with "Agent object is not callable". It wrapped the instance in
a function that returned the same object every time, and printed a warning:
shared state, not isolated. In June the `co create` template switched to
`host(agent)`. In August the warning was removed as noise. `co ai`'s own
server passed an instance as well. So the most common way to run an agent was
the one path where every conversation used the same object.

An Agent keeps the turn it is working on in `self.current_session`. With one
object and two conversations at the same moment, the second overwrote the
first mid-turn. One person's question disappeared from their history, and
their answer was written into someone else's. On a single-user agent that
happens whenever a scheduled job runs while you chat, or a message comes in
on a chat channel as you type.

The fix follows the original design. `co ai` and the template now pass a
function: `host(lambda: create_agent(role="coding"))`. We looked at rebuilding
an Agent from an instance instead, but that only works if the Agent remembers
everything done to it after construction, and `co ai` itself sets fields after
building its agent. A copy fails too: the model client holds a lock that
cannot be copied. So an instance keeps its plain meaning, one object, and a
Host given one now runs one turn at a time. Projects that still pass an
instance keep working and never mix conversations.

The test starts a real Host and connects two real clients with their own keys,
asking at the same moment. With a function, both turns run together and each
history holds only its own question and answer. With an instance, they run one
after the other. On the old code, the instance case ran both turns at once.
