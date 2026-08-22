# The Tested Agent Was Not the Running Agent

A developer could change the explore agent's model, tools, or iteration limit,
run its focused test, and get a green result. Then they could start `co ai` and
see none of those changes.

The test was honest about the object it created. The problem was that the
object was not part of the running product. An older Python registry built
explore and plan agents from two prompt files under `cli/co_ai`. Meanwhile,
`co ai` installed the subagents plugin, which discovered different `AGENT.md`
files under `useful_plugins/builtin_agents`. The names matched closely enough
to hide the split.

Keeping both paths looked harmless because each was internally coherent. The
registry had a factory and a test; the plugin had discovery, overrides, and its
own tests. But coherence on both sides made the failure more convincing. A
green registry test suggested that the coding assistant had changed when only
an unreachable definition had changed.

We considered making the registry authoritative. That would have moved the
running system away from the plugin's existing project, user, and built-in
discovery order. The product already depended on that order, so the smaller
and more truthful fix was to remove the parallel registry and its shadow
prompts.

The replacement regression follows the path the product follows. It loads the
built-in explore `AGENT.md`, lets the task tool resolve its real tools, and
captures the subagent that would run. The assertions cover the read-only
prompt, model-independent tool set, iteration limit, and delegated task. A
second check lists the old shadow locations so a future copy cannot quietly
restore the ambiguity.

Dead code is not harmless when it looks like a supported extension point. It
attracts changes, documentation, and tests, then turns all three into false
evidence. A source of truth is only useful when the running system and the
test suite reach it by the same route.
