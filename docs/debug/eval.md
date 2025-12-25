# Evals

Run and manage agent evals with `co eval`. Test agent behavior, track results over time, use LLM-as-judge for semantic evaluation.

## Quick Start

```bash
# Run all evals in .co/evals/
co eval

# Run specific eval
co eval wikipedia_lookup

# Run with specific agent file
co eval --agent my_agent.py
```

## Creating Evals

Create YAML files in `.co/evals/`:

```yaml
# .co/evals/wikipedia_lookup.yaml
name: wikipedia_lookup
agent: agent.py
turns:
- input: Go to Wikipedia and find when the Eiffel Tower was built.
  expected: Contains 1889 or late 1880s
```

### Minimal Eval

```yaml
name: simple_greeting
agent: agent.py
turns:
- input: Say hello to Alice
  expected: Greeting includes Alice's name
```

### Multi-Turn Conversation

Turns run sequentially within the same agent session, simulating a conversation:

```yaml
name: multi_turn_chat
agent: agent.py
turns:
- input: My name is Bob
  expected: Acknowledges the name Bob
- input: What's my name?
  expected: Remembers and says Bob
```

## YAML Format

```yaml
name: eval_name                    # Eval identifier
agent: agent.py                    # Path to agent file (required)
created: '2025-12-25 14:30:00'     # Auto-generated
updated: '2025-12-25 18:35:58'     # Auto-updated on each run
runs: 8                            # Total run count

turns:
- input: User input text           # What to send to agent
  output: Agent response           # Captured from agent
  expected: What we expect         # For LLM judge evaluation
  pass: true                       # Judge result (true/false)
  analysis: Output contains...     # Judge explanation
  tools_called:                    # Tools the agent used
  - open_browser(headless=False)
  - go_to(url='https://...')
  tokens: 62533                    # Total tokens used
  cost: 0.0491                     # Total cost in USD
  ts: '2025-12-25 18:35:58'        # Timestamp
  run: 8                           # Run number
  history: '[...]'                 # Previous runs (JSON array)
```

## LLM-as-Judge

When `expected` is set, an LLM judges if the output satisfies the criteria:

```yaml
turns:
- input: What's 2+2?
  expected: Answer is 4
```

The judge considers:
- Semantic similarity (not exact match)
- Key information presence
- Intent fulfillment

Results stored as:
- `pass: true/false` - Did it pass?
- `analysis: "..."` - Why it passed/failed

## History Tracking

Each run is preserved in `history` as a JSON array:

```yaml
history: |
  [
  {"ts": "2025-12-25 18:35:58", "pass": true, "tokens": 62584, "cost": 0.05},
  {"ts": "2025-12-25 18:25:06", "pass": true, "tokens": 54879, "cost": 0.04},
  {"ts": "2025-12-25 18:20:25", "pass": false, "tokens": 40147, "cost": 0.03}]
```

Use history to:
- Track stability across runs
- Compare token usage and costs
- Identify regressions

## Agent File Structure

Your agent file must export an `agent` variable:

```python
# agent.py
from connectonion import Agent

agent = Agent(
    name="my_agent",
    tools=[...],
    model="co/gemini-2.5-pro"
)

if __name__ == "__main__":
    agent.input("Interactive mode...")
```

## CLI Options

```bash
# Run all evals
co eval

# Run specific eval by name
co eval my_eval_name

# Override agent file (ignores YAML agent field)
co eval --agent custom_agent.py
co eval -a custom_agent.py
```

## Output

```
Loading: agent.py
Running: wikipedia_lookup
  input: Go to Wikipedia and find when the Eiffel Tower...
  ✓ Output contains 1889 and height information...
✓ wikipedia_lookup completed

                    Eval Results
┌──────────────────┬────────┬────────────┬────────────┐
│ Eval             │ Status │ Expected   │ Output     │
├──────────────────┼────────┼────────────┼────────────┤
│ wikipedia_lookup │ ✓ pass │ Contains...│ The Eiff...│
└──────────────────┴────────┴────────────┴────────────┘

✓ 1 passed
```

## Best Practices

### Write Good Expected Criteria

```yaml
# Bad - too specific
expected: "The Eiffel Tower was built in 1889"

# Good - semantic criteria
expected: Contains the year 1889 and mentions Paris or France
```

### Keep Evals Focused

```yaml
# Bad - testing too many things
- input: Go to Wikipedia, find the Eiffel Tower, take a screenshot, and summarize

# Good - one thing at a time
- input: Go to Wikipedia and find the Eiffel Tower height
  expected: Height around 300-330 meters
```

### Use Multi-Turn for Conversations

```yaml
turns:
- input: Remember that my favorite color is blue
  expected: Acknowledges the color preference
- input: What's my favorite color?
  expected: Says blue
```

## File Organization

```
.co/evals/
├── 1_basic_greeting.yaml      # Number prefix for ordering
├── 2_wikipedia_lookup.yaml
├── 3_multi_turn_chat.yaml
└── 4_complex_workflow.yaml
```

## Troubleshooting

### "No agent specified"

Add `agent: agent.py` to YAML or use `--agent` flag:

```bash
co eval --agent my_agent.py
```

### "No 'agent' instance found"

Ensure your agent file exports `agent`:

```python
agent = Agent("name", ...)  # Must be named 'agent'
```

### Eval passes but shouldn't (or vice versa)

Check the `analysis` field to understand the judge's reasoning. Adjust `expected` to be more specific.
