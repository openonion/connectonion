# Session Logging and Eval Format

## Problem

When developing AI agents:
1. Agent runs are slow (LLM calls take time)
2. We run the same prompt many times during development
3. We need to compare: "after changing this prompt, what's different?"
4. We need regression testing: "does new prompt still work for old cases?"

## Requirements

1. **Log** - Save full session (inputs, tool calls, results, messages)
2. **Replay** - Load saved messages to restore context
3. **Eval** - Mark expected behavior, LLM judges if it matches
4. **Edit** - Developers can view/edit in VS Code

## Format Decision: YAML with JSON String for Messages

```yaml
name: gmail_agent
timestamp: 2024-11-27 11:39:58

turns:
  - input: "check my emails"
    model: "gemini-2.5-pro"
    duration_ms: 11200
    tokens: 1234
    cost: 0.01
    tools_called: [get_emails]
    result: "You have 3 emails"
    messages: '[{"role":"system","content":"..."},{"role":"user","content":"check my emails"},{"role":"assistant","content":"You have 3 emails"}]'
    eval:
      expect_tools: [get_emails]
      expect_result: "shows email list"

  - input: "reply to first saying thanks"
    model: "gemini-2.5-pro"
    duration_ms: 8500
    tokens: 2345
    cost: 0.02
    tools_called: [send_email]
    result: "Reply sent"
    messages: '[{"role":"system","content":"..."},{"role":"user","content":"reply to first saying thanks"},{"role":"assistant","content":"Reply sent"}]'
    eval:
      expect_tools: [send_email]
      expect_result: "reply sent"
```

## Why This Format

**YAML** for readable fields (input, tools, result, cost)

**JSON string** for messages:
- Won't break YAML (prompts with colons, quotes, etc.)
- One line = simple to parse
- Already JSON in code, easy to `json.loads()`

**One turn = one user input**:
- System message + user input + tool calls + final response
- No second user input within a turn
- Second user input = next turn

## Field Reference

| Field | Type | Description |
|-------|------|-------------|
| `input` | string | User input for this turn |
| `model` | string | LLM model used |
| `duration_ms` | int | How long the turn took |
| `tokens` | int | Total tokens used |
| `cost` | float | Cost in USD |
| `tools_called` | list | Tools that were called |
| `result` | string | Agent's final response |
| `messages` | JSON string | Message context window |
| `eval` | object | Optional expectations |
| `eval.expect_tools` | list | Expected tools |
| `eval.expect_result` | string | Expected result description |

## File Structure

```
.co/
  sessions/
    gmail_agent_2024-11-27_11-39-58.yaml   # Auto-saved
```

## Workflow

1. Run agent → auto-saves to `.co/sessions/`
2. Add `eval:` to turns you want to test
3. Change prompt → run evals
4. LLM judges: did tools match? Is result similar?

## Implementation

```python
# Save
turn = {
    'input': user_input,
    'model': self.llm.model,
    'duration_ms': duration,
    'tokens': usage.input_tokens + usage.output_tokens,
    'cost': usage.cost,
    'tools_called': [tc.name for tc in tool_calls],
    'result': response,
    'messages': json.dumps(messages),
}

# Load
session = yaml.safe_load(file)
messages = json.loads(turn['messages'])
```

## Alternatives Rejected

- **JSONL** - Crash-unsafe, hard to read
- **Pure YAML** - Prompts break format (colons, quotes)
- **Multi-line JSON** - Unnecessary complexity
- **Separate message files** - Too complex