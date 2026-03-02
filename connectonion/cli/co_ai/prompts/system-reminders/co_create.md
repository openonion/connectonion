---
name: co-create
triggers:
  - tool: bash
    command_pattern: "co create*"
---

<system-reminder>
Project scaffolded. Now:
1. `cd` into the created project directory
2. All subsequent file edits, reads, and bash commands should run from inside that directory
3. Edit `agent.py` to add the custom tools from your plan
</system-reminder>
