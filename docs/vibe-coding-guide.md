# Vibe coding with ConnectOnion

Start from a working ConnectOnion project, give your coding assistant the
framework context that ships with it, and describe the behavior you want.

## Claude Code

The official ConnectOnion plugin is the shortest path:

The build workflow requires plugin **1.2.0 or later**. Existing installations
should [update the plugin first](claude-code-plugin.md#install-or-update).

```text
/plugin marketplace add openonion/connectonion-claude-plugin
/plugin install connectonion@connectonion-marketplace
```

Create and open an agent:

```bash
co create my-agent
cd my-agent
claude
```

Then run `/connectonion:aaron-build-my-agent`, or ask Claude Code to read
`.co/docs/README.md` before making a specific change:

```text
Read .co/docs/README.md and the relevant design decisions. Add a skill that
summarizes new support emails, with tests, and keep agent.py unchanged.
```

See [Claude Code plugin](claude-code-plugin.md) for review commands and the
division between plugin skills and project documentation.

## Cursor and other coding assistants

The same project context works without the plugin:

1. Run `co create my-agent` or `co init ./` in an existing project.
2. Add `.co/docs/README.md` and the relevant linked pages to the assistant's
   context.
3. Describe one behavior change and ask for tests with it.
4. Review the diff and run the project's checks before accepting it.

If the editor cannot read hidden directories, attach the relevant `.co/docs/`
files explicitly. You can also use the documentation website's **Copy All
Docs** action.

## Prompt examples

Start with the outcome and name the constraints that matter:

```text
Read .co/docs/README.md. Add a weather skill to this agent. Keep agent.py
small, put the procedure in .co/skills/weather/SKILL.md, and add an offline
test for skill discovery.
```

```text
Review this ConnectOnion agent against the design decisions in
.co/docs/design-decisions/. Report correctness problems before style issues;
do not edit files yet.
```

```text
Add a stateful browser tool following the installed ConnectOnion docs. Explain
why state is required, make the smallest change, and run the relevant tests.
```

## Why this works

ConnectOnion keeps the generated agent deliberately small. The stable project
shape comes from `co create`; skills hold specialized procedures; `.co/docs/`
grounds coding assistants in the framework version the project actually uses.
That separation lets the assistant change behavior without inventing another
template or copying framework internals into the project.
