---
name: plan-mode
triggers:
  - tool: enter_plan_mode
---

<system-reminder>
You are now in plan mode. Write an agent spec — not implementation steps.

Note: If unclear about ConnectOnion concepts, load relevant guides first. Start with `load_guide("best-practices")` for core principles, then load other guides as needed (tools, events, llm_do, etc).

## Your plan MUST use this YAML format:

```yaml
agent: <name>
scaffold: co create <name> --template <template>

tools:
  - name: <tool_name>
    input: <param> (<type>)
    output: <what it returns>        # or:
    effect: <what it does to the world>

evals:
  - input: "<example user request>"
    effect: <what happens>
    output: "<example response>"
```

## Scaffolding:
`co create <name>` — one template, the same agent `co ai` runs. Specialise it
with skills in `.co/skills/`, not with a different template.

## Rules:
- `scaffold` line is REQUIRED — this is the first command run after approval
- After user approves: run `bash("co create <name>")` then add skills / edit `agent.py`
- NEVER use `write` to create agent files manually
- Only use glob/grep/read_file to explore if needed, then write_plan(), then exit_plan_and_implement()
</system-reminder>
