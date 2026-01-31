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
# Asks user to choose: 1=Yes, 2=Yes to all, 3=No + feedback
# Returns: "Wrote 15 bytes to hello.py" or feedback message
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

## Approval Options

When a file change is proposed, user sees:

```
╭─── Changes to hello.py ────────────────────────╮
│ --- a/hello.py                                 │
│ +++ b/hello.py                                 │
│ @@ -1,2 +1,3 @@                                │
│  def hello():                                  │
│ -    pass                                      │
│ +    print("Hello!")                           │
╰────────────────────────────────────────────────╯

Choose an option:
  1 - Yes, apply this change
  2 - Yes to all (auto-approve for this session)
  3 - No, and tell agent what to do instead

Apply changes to hello.py? [1/2/3]:
```

| Option | Effect |
|--------|--------|
| **1** | Apply this change, ask again for next change |
| **2** | Apply this and all future changes (session-wide) |
| **3** | Reject + provide feedback for agent to try again |

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
# User sees diff and chooses 1, 2, or 3
# If 3: User provides feedback, agent receives it and tries again
```

## Feedback Flow

When user chooses option 3 (reject):

1. User is prompted: "What should the agent do instead?"
2. User types feedback, e.g., "use snake_case for function names"
3. Agent receives: `"User rejected changes to hello.py. Feedback: use snake_case for function names"`
4. Agent can retry with the feedback

## Common Use Cases

```python
# Interactive coding with approval
writer = DiffWriter()
agent = Agent("coder", tools=[writer])

# CI/CD automation - skip prompts
writer = DiffWriter(auto_approve=True)
agent = Agent("automation", tools=[writer])

# Preview changes only
diff = writer.diff("config.py", new_config)
print(diff)
```

## Customizing

Need to modify DiffWriter's behavior? Copy the source to your project:

```bash
co copy diff_writer
```

Then import from your local copy:

```python
# from connectonion import DiffWriter  # Before
from tools.diff_writer import DiffWriter  # After - customize freely!
```
