# Built-in Skills

Pre-built skills you can copy into your project and invoke with `/skill-name`.

## Quick Reference

| Skill | Purpose | Invoke |
|-------|---------|--------|
| [ship-feature](ship-feature.md) | Ship a feature end-to-end: tests → docs → docs-site → release | `/ship-feature` |

## How to Use

Skills are markdown workflows, not imported code. Copy them into your project:

```bash
co copy ship-feature
# → .co/skills/ship-feature/SKILL.md
```

Then with the `skills` plugin enabled, just type:

```
/ship-feature
```

## Setup

```python
from connectonion import Agent
from connectonion.useful_plugins import skills, tool_approval

agent = Agent("assistant", tools=[...], plugins=[skills, tool_approval])
```

## How Skills Differ from Tools and Plugins

| | Tools | Plugins | Skills |
|---|---|---|---|
| Format | Python `.py` | Python `.py` | Markdown `SKILL.md` |
| Invoked by | LLM | Event hooks | `/command` or `skill()` |
| Customized via | Copy + edit code | Copy + edit code | Copy + edit markdown |
| Permissions | Per tool | Per plugin | Scoped to skill turn |

## Adding Your Own

```bash
mkdir -p .co/skills/my-skill
cat > .co/skills/my-skill/SKILL.md <<'EOF'
---
name: my-skill
description: What this skill does
tools:
  - Bash(git *)
  - read_file
---

# My Skill

Step 1: ...
Step 2: ...
EOF
```

## See Also

- [Skills Feature](../features/skills.md) — Full skills system documentation
- [co copy](../cli/copy.md) — Copy skills to your project
- [skills plugin](../useful_plugins/skills.md) — Plugin that enables `/command` invocation
