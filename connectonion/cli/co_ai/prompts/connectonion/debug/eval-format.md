# Eval YAML Format

Evals are stored in `.co/evals/{input_slug}.yaml`. File is named from the first user input (slugified). Same input sequence = same file with run tracking. Log = Eval (same format, add `expected` field for tests).

## File Structure

```
.co/evals/
├── say_hello_to_alice.yaml              # Eval metadata + turns summary
├── say_hello_to_alice/
│   ├── run_1.yaml                       # Run 1: metadata + messages as JSON
│   └── run_2.yaml                       # Run 2: metadata + messages as JSON
├── open_hacker_news_and_summarize.yaml
└── open_hacker_news_and_summarize/
    └── run_1.yaml
```

## Eval Summary YAML

```yaml
name: say_hello_to_alice
created: '2025-12-25 11:56:26'
updated: '2025-12-25 11:56:56'
runs: 2
model: gemini-2.5-flash
turns:
- input: Say hello to Alice
  run: 2
  output: Hello, Alice!
  tools_called:
  - greet(name='Alice')
  expected: ''                            # For eval: expected output
  evaluation: ''                          # For eval: pass/fail/notes
  meta: '{"tokens": 155, "cost": 0.0, "duration_ms": 3595, "ts": "2025-12-25 11:56:56"}'
  history:
  - run: 1
    output: Hello, Alice!
    tools_called:
    - greet(name='Alice')
    expected: ''
    evaluation: ''
    meta: '{"tokens": 155, "cost": 0.0, "duration_ms": 4438, "ts": "2025-12-25 11:56:26"}'
```

The `meta` field is a compact JSON string containing tokens, cost, duration, and timestamp.

## Run YAML Format

Each run has its own YAML file with metadata and messages:

```yaml
system_prompt: "You are a helpful assistant..."
model: "claude-sonnet-4-5"
cwd: "/path/to/project"
tokens: 1314
cost: 0.0015
duration_ms: 6162
timestamp: "2025-12-25 12:50:44"
messages: |
  [
    {"role": "system", "content": "You are a helpful assistant..."},
    {"role": "user", "content": "Say hello to Alice"},
    {"role": "assistant", "tool_calls": [{"id": "...", "function": {"name": "greet", "arguments": "{\"name\": \"Alice\"}"}}]},
    {"role": "tool", "content": "Hello, Alice!", "tool_call_id": "..."}
  ]
```

**Key fields:**
- `system_prompt`: The agent's system prompt (easy to access)
- `model`: Which model was used
- `cwd`: Working directory (for re-execution)
- `tokens`, `cost`, `duration_ms`: Performance metrics
- `messages`: Full message history as multi-line JSON (API format)

## Design Rationale

### Why file naming from input (not agent name)?

Same input = same eval file. This enables:
- **Run comparison**: See how outputs change across runs
- **Regression testing**: Same input should produce consistent results
- **History tracking**: Previous runs preserved in `history` array

### Why YAML with embedded JSON for messages?

1. **Clean separation**: YAML for readable metadata, JSON for API-compatible messages
2. **Easy to navigate**: Multi-line JSON is scannable
3. **Reproducibility**: `cwd` and `system_prompt` stored for re-execution
4. **Single file per run**: No need to manage multiple files

### Why runs and history?

```yaml
turns:
- input: Say hello to Alice
  run: 2                    # Latest run is the main entry
  output: Hello, Alice!
  history:                  # Previous runs for comparison
  - run: 1
    output: Hello, Alice!
```

- Latest run is always at top level (easy to see current state)
- History preserves all previous runs for regression analysis
- Compare outputs across model versions or code changes

## Usage

### Quick check latest run
```bash
head -30 .co/evals/say_hello_to_alice.yaml
```

### Load messages for replay
```python
import json
import yaml

def load_messages(eval_dir: str, run: int = 1) -> list:
    """Load messages from run YAML file."""
    with open(f"{eval_dir}/run_{run}.yaml") as f:
        data = yaml.safe_load(f)
    return json.loads(data['messages'])

# Load run 1 messages
messages = load_messages(".co/evals/say_hello_to_alice", run=1)
```

### Load run metadata
```python
import yaml

with open('.co/evals/say_hello_to_alice/run_1.yaml') as f:
    run_data = yaml.safe_load(f)

print(f"Model: {run_data['model']}")
print(f"System prompt: {run_data['system_prompt']}")
print(f"CWD: {run_data['cwd']}")
print(f"Tokens: {run_data['tokens']}, Cost: ${run_data['cost']}")
```

### Compare runs
```python
import yaml

with open('.co/evals/say_hello_to_alice.yaml') as f:
    data = yaml.safe_load(f)

turn = data['turns'][0]
print(f"Run {turn['run']}: {turn['output']}")

for hist in turn.get('history', []):
    print(f"Run {hist['run']}: {hist['output']}")
```

### Add expected results for eval
```yaml
turns:
- input: Say hello to Alice
  run: 2
  output: Hello, Alice!
  expected: "Hello, Alice!"           # What we expect
  evaluation: "pass"                   # Did it pass?
```

### Parse metadata
```python
import json

turn = data['turns'][0]
meta = json.loads(turn['meta'])
print(f"Tokens: {meta['tokens']}, Cost: ${meta['cost']}, Duration: {meta['duration_ms']}ms")
```

### Get total runs
```bash
yq '.runs' .co/evals/say_hello_to_alice.yaml
```
