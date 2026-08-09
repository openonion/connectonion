# Templates

There is one template. `co create` scaffolds the same agent `co ai` runs, and
you specialise it with skills.

```bash
co create my-agent                                          # the co-ai template
co create my-agent --template custom --description "..."    # AI writes agent.py
```

## Why one

There used to be six — `minimal`, `coder`, `browser`, `hosted-browser`,
`web-research`, `co-ai`. They differed mostly by their prompt, they drifted
apart as the SDK moved, and four of the six never called `host()`, so
`co create` followed by `co deploy` dead-stopped.

Starting from a different skeleton is the wrong axis to vary. The agent is the
same in every case: files, shell, browser, todos, sub-agents. What
differs between a coding assistant and a LinkedIn poster is *what it knows how
to do* — and that is a skill, not a scaffold.

## What you get

```
my-agent/
├── agent.py           # create_agent() + host(), ~5 lines
├── Dockerfile         # Chrome under Xvfb, so browser skills work deployed
├── requirements.txt
├── .env               # API keys
└── .co/
    ├── host.yaml      # name, entrypoint, trust, summary, examples
    ├── docs/          # full documentation, for vibe coding
    └── skills/        # ← where your agent becomes yours
```

`agent.py` is deliberately short:

```python
from connectonion import host
from connectonion.cli.co_ai.agent import create_agent

agent = create_agent(role="coding")

host(agent)
```

## Specialising it

**Skills** are the procedures your agent follows. Drop one in
`.co/skills/<name>/SKILL.md` and it is discovered automatically:

```bash
co skills copy commit                               # from the bundled library
co deploy --skills ~/skills/linkedin-post-submit    # or bring your own
```

See [Deploy › Skills](../network/deploy.md#skills).

**Roles** set what kind of agent it is. `role="coding"` adds the software
engineering doctrine — read before editing, match the surrounding style, don't
over-engineer, `file:line` references, git. An agent that posts to LinkedIn or
answers support tickets wants none of that:

```python
agent = create_agent(role=None)     # no domain, behaviour only
```

Roles ship with the SDK in `connectonion/cli/co_ai/prompts/roles/`. Everything
else — how the agent plans, asks, reports, and handles actions it cannot take
back — lives in the shared prompt, so it improves when the SDK does.

## The custom template

`--template custom` still exists. It asks an LLM to write `agent.py` from a
description, for when you want something structurally different rather than a
specialised co-ai:

```bash
co create my-agent --template custom \
  --description "watches an RSS feed and files issues"
```

## Retired templates

`minimal`, `coder`, `browser`, `hosted-browser`, and `web-research` were
removed. Passing one now exits 1 and says so. Use the default template plus
skills.

## Next Steps

- [CLI Create Command](../cli/create.md) - Full `co create` options
- [Deploy](../network/deploy.md) - Shipping it, and bundling skills
- [Tools Documentation](../concepts/tools.md) - Creating custom tools
