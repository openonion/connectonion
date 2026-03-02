# Tool: Plan Mode

Design the agent spec before building. The plan is a **contract** of what the final agent looks like — not implementation steps.

## When to Use

- **New agent** — always design the spec first for user approval
- **Existing agent changes** — read the files first, then make changes directly (no plan needed)

## When NOT to Use

- Modifying an existing agent (read files, then edit directly)
- General coding tasks unrelated to agent creation

## The Plan is an Agent Spec

The plan shows the agent's **contract**: what inputs it accepts, what tools it uses, what effects it produces, what output it returns.

After user approves the spec, scaffold with `co create`, then edit `agent.py`.

## Plan Format

```yaml
agent: duplicate-cleaner
scaffold: co create duplicate-cleaner  # or --template browser/coder/web-research

tools:
  - name: list_files
    input: dir (str)
    output: list of {path, size, hash}

  - name: find_duplicates
    input: files (list)
    output: groups of duplicate paths

  - name: delete_file
    input: path (str)
    effect: deletes file from disk
    output: confirmation message

evals:
  - input: "clean duplicates in ~/downloads"
    effect: scans directory, groups duplicates, asks user confirmation, deletes
    output: "Deleted 5 duplicate files, freed 120MB"
```

## Workflow

1. `enter_plan_mode()` — switch to spec-design mode
2. Ask clarifying questions if the design is unclear
3. `write_plan()` — write the agent spec in YAML format above
4. `exit_plan_mode()` — user reviews and approves the spec
5. After approval: `co create <name> --template <template>` then edit `agent.py`

## READ-ONLY Restrictions

In plan mode you can ONLY:
- Write the plan file
- Ask user questions

You CANNOT:
- Create or modify any code files
- Run commands (except `co create` after plan is approved)
