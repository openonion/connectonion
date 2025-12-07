# Session YAML Format

Sessions are stored in `.co/sessions/{agent_name}.yaml`. One file per agent (not per session).

## Structure

```yaml
# ===== METADATA (compact) =====
name: oo
created: '2025-12-03 10:12:44'
updated: '2025-12-03 10:15:30'
total_cost: 0.0523
total_tokens: 25000

# ===== TURNS SUMMARY (all turns visible at a glance) =====
turns:
  - turn: 1
    input: list files in current directory
    result: 'Found 10 files: .co/, .env, README.md, agent.py...'
    model: co/gemini-2.5-pro
    duration_ms: 8770
    tokens: 15006
    cost: 0.0152
    tools_called:
    - run(command='ls -la')
    timestamp: '2025-12-03 10:12:50'
    # Easy to add for eval:
    # expected: Should list all files
    # passed: true

  - turn: 2
    input: create hello.py that prints hello world
    result: Created hello.py with a simple hello world program.
    model: co/gemini-2.5-pro
    duration_ms: 5230
    tokens: 9994
    cost: 0.0371
    tools_called:
    - write(path='hello.py', content='print("Hello, World!")')
    timestamp: '2025-12-03 10:15:30'

  - turn: 3
    input: run the tests
    result: All 5 tests passed successfully.
    model: co/gemini-2.5-pro
    duration_ms: 12500
    tokens: 8500
    cost: 0.0289
    tools_called:
    - run(command='pytest')
    timestamp: '2025-12-03 10:18:00'

# ===== DETAIL SECTION (scroll down) =====
system_prompt: You are a coding agent. You have access to tools to help complete tasks.

messages:
  1:
    - role: user
      content: list files in current directory

    - role: assistant
      content: null
      tool_calls:
        - id: call_abc123
          type: function
          function:
            name: run
            arguments: '{"command": "ls -la"}'

    - role: tool
      tool_call_id: call_abc123
      content: |
        total 20
        drwxr-xr-x  5 user staff  160 Dec  3 10:12 .
        drwxr-xr-x 10 user staff  320 Dec  3 10:00 ..
        drwxr-xr-x  3 user staff   96 Dec  3 10:12 .co
        -rw-r--r--  1 user staff  100 Dec  3 10:12 .env
        -rw-r--r--  1 user staff 1200 Dec  3 10:12 README.md

    - role: assistant
      content: 'Found 10 files: .co/, .env, README.md, agent.py...'

  2:
    - role: user
      content: create hello.py that prints hello world

    - role: assistant
      content: null
      tool_calls:
        - id: call_def456
          type: function
          function:
            name: write
            arguments: '{"path": "hello.py", "content": "print(\"Hello, World!\")"}'

    - role: tool
      tool_call_id: call_def456
      content: File written successfully

    - role: assistant
      content: Created hello.py with a simple hello world program.

  3:
    - role: user
      content: run the tests

    - role: assistant
      content: null
      tool_calls:
        - id: call_ghi789
          type: function
          function:
            name: run
            arguments: '{"command": "pytest"}'

    - role: tool
      tool_call_id: call_ghi789
      content: |
        ===== test session starts =====
        collected 5 items
        test_hello.py .....
        ===== 5 passed in 0.12s =====

    - role: assistant
      content: All 5 tests passed successfully.
```

## Design Rationale

### Why separate turns summary from messages?

The core problem: **Turn 2's summary gets buried after Turn 1's messages.**

With messages nested in turns:
```yaml
turns:
  - turn: 1
    input: ...
    messages:        # 50+ lines of messages
      ...
  - turn: 2          # ← Buried! Need to scroll past turn 1's messages
    input: ...
```

With messages at end:
```yaml
turns:               # All summaries together - instant overview
  - turn: 1
    input: ...
  - turn: 2
    input: ...
  - turn: 3
    input: ...
messages:            # Detail at end - scroll when needed
  1: [...]
  2: [...]
```

### Why block style (not flow style)?

Flow style is compact but not extensible:
```yaml
# Hard to add fields, lines get too long
- {turn: 1, input: "...", result: "...", cost: 0.01, expected: "...", passed: true, ...}
```

Block style is extensible and editable:
```yaml
# Easy to add fields for eval
- turn: 1
  input: list files
  result: Found 10 files
  cost: 0.0152
  expected: Should list all files    # Easy to add
  passed: true                        # Easy to add
```

### Why messages keyed by turn number?

- Easy to find: "What happened in turn 3?" → Look at `messages.3`
- No ambiguity: Turn number is the key
- Easy to extend: Add new turns without reordering

## Usage

### Quick eval (see all turns at once)
```bash
# First 40 lines shows all turn summaries
head -40 .co/sessions/oo.yaml
```

### Load all messages for resume
```python
import yaml

with open('.co/sessions/oo.yaml') as f:
    session = yaml.safe_load(f)

# Reconstruct full message list
messages = [{"role": "system", "content": session['system_prompt']}]

for turn_num in sorted(session['messages'].keys()):
    messages.extend(session['messages'][turn_num])

agent.current_session['messages'] = messages
```

### Replay specific turn (e.g., turn 2)
```python
import yaml

with open('.co/sessions/oo.yaml') as f:
    session = yaml.safe_load(f)

# Build context: system + previous turns + target's user input
target_turn = 2
messages = [{"role": "system", "content": session['system_prompt']}]

# Add all messages from previous turns
for turn_num in range(1, target_turn):
    messages.extend(session['messages'][turn_num])

# Add only user input from target turn
target_input = session['turns'][target_turn - 1]['input']
messages.append({"role": "user", "content": target_input})

# Run agent with this context
agent.current_session['messages'] = messages
result = agent._run_iteration_loop(max_iterations=10)
```

### Filter turns summary only
```bash
yq '.turns[] | {turn, input, result, cost}' .co/sessions/oo.yaml
```

### Get total cost
```bash
yq '.total_cost' .co/sessions/oo.yaml
```

### Debug specific turn's messages
```bash
yq '.messages.2' .co/sessions/oo.yaml
```

### Add expected results for eval
```bash
# Manually edit to add expected/passed fields
vim .co/sessions/oo.yaml
```

```yaml
turns:
  - turn: 1
    input: list files
    result: Found 10 files
    expected: Should list all files in directory  # Added for eval
    passed: true                                   # Added for eval
```
