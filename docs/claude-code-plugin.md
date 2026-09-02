# Claude Code plugin

ConnectOnion has an official Claude Code plugin for framework development and
code review.

## Install or update

Install it from the ConnectOnion marketplace inside Claude Code:

```text
/plugin marketplace add openonion/connectonion-claude-plugin
/plugin install connectonion@connectonion-marketplace
/reload-plugins
```

The single-template build and review workflows require plugin **1.2.0 or
later**. If the plugin is already installed, refresh the marketplace and update
the cached plugin:

```text
/plugin marketplace update connectonion-marketplace
/plugin update connectonion@connectonion-marketplace
/reload-plugins
```

## Use it with an agent

Create a project and open it in Claude Code:

```bash
co create my-agent
cd my-agent
claude
```

Ask the plugin to build or specialize the agent:

```text
/connectonion:aaron-build-my-agent
```

In a generated `co-ai` project, the build skill reads `.co/docs/`, keeps the
small `create_agent(...) + host(...)` entrypoint, and puts specialized
procedures in `.co/skills/`. In a direct SDK project, it preserves the existing
`Agent(...)` lifecycle.

Use the plugin to review the project after making changes:

```text
/connectonion:aaron-review-my-code .
/connectonion:linus-review-my-code .
```

The plugin repository owns the source and current plugin documentation. See the
[ConnectOnion Claude Code plugin repository](https://github.com/openonion/connectonion-claude-plugin)
for those details.

## Give Claude Code framework context

`co create` and `co init ./` put the framework reference in `.co/docs/`. The
plugin provides explicit build and review procedures; the project docs provide
the version-specific ConnectOnion API and design context.

Tell Claude Code to read that context before a framework-wide change:

```text
Read .co/docs/README.md and the relevant design decisions, then add a skill
that watches an RSS feed and files an issue for each new item.
```

Be explicit about the files that matter. Do not rely on an editor discovering
every hidden project file automatically.

## Why there is only one template

ConnectOnion used to ship several agent templates. They drifted as the SDK
changed, so `co create` now starts from one small, deployable `co-ai` agent.
Add skills in `.co/skills/` to specialize it; use the Claude Code plugin to
build or review those changes.

See [Templates](templates/) for the current project shape and
[Vibe Coding](vibe-coding-guide.md) for an editor-agnostic workflow.
