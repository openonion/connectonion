# DiffWriter

Human-in-the-loop file writing with diff display and approval.

## Installation

```python
from connectonion import DiffWriter

writer = DiffWriter()
```

## API

### write(path, content)

Write content to a file with diff display and user approval.

```python
result = writer.write("hello.py", "print('hello')")
# Shows colorized diff
# Asks: "Apply changes to hello.py? [y/n]"
# Returns: "Wrote 15 bytes to hello.py" or "Changes rejected by user"
```

### diff(path, content)

Show diff without writing (preview mode).

```python
diff_text = writer.diff("hello.py", "print('hello')")
# Returns the diff string without writing
```

### read(path)

Read file contents.

```python
content = writer.read("hello.py")
# Returns: "print('hello')"
```

## Options

### auto_approve

Skip approval prompts (for automation).

```python
# Ask for approval (default)
writer = DiffWriter(auto_approve=False)

# Auto-approve all writes
writer = DiffWriter(auto_approve=True)
```

## Use with Agent

```python
from connectonion import Agent, DiffWriter

writer = DiffWriter()
agent = Agent("coder", tools=[writer])

agent.input("create a hello.py file with a hello world function")
# Agent calls writer.write()
# User sees diff and approves
```

## Visual Output

```
╭─── Changes to hello.py ────────────────────────╮
│ --- /dev/null                                  │
│ +++ b/hello.py                                 │
│ @@ -0,0 +1,3 @@                                │
│ +def hello():                                  │
│ +    print("Hello, World!")                    │
│ +                                              │
╰────────────────────────────────────────────────╯
Apply changes to hello.py? [y/n]:
```

## Common Use Cases

```python
# Coding agent with human approval
writer = DiffWriter()
agent = Agent("coder", tools=[writer, bash, read_file])

# CI/CD - auto-approve
writer = DiffWriter(auto_approve=True)
agent = Agent("automation", tools=[writer])

# Preview changes only
diff = writer.diff("config.py", new_config)
print(diff)  # Show what would change
```
