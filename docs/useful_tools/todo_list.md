# TodoList

Task tracking tool for agents to manage complex, multi-step tasks.

## Usage

**Option 1: Import directly**

```python
from connectonion import TodoList

agent = Agent("worker", tools=[TodoList()])
```

**Option 2: Copy and customize**

```bash
co copy todo_list
```

```python
from tools.todo_list import TodoList  # Your local copy
```

## Installation

```python
from connectonion import TodoList

todo = TodoList()
```

## Why Use TodoList?

- **Track progress** on complex tasks with multiple steps
- **Show users** what the agent is working on
- **Organize** multi-step workflows
- **Prevent** forgetting steps in complex tasks

## When to Use

Use TodoList when:
- Task requires **3+ distinct steps**
- User provides **multiple tasks** (numbered or comma-separated)
- Task requires **careful planning**
- You want to show **progress** to the user

Don't use when:
- Task is **trivial** (1-2 simple steps)
- Task is **purely conversational**

## API

### add(content, active_form)

Add a new pending task.

```python
todo.add("Fix authentication bug", "Fixing authentication bug")
todo.add("Run tests", "Running tests")
todo.add("Update docs", "Updating docs")
```

### start(content)

Mark a task as in_progress. Only one task can be in_progress at a time.

```python
todo.start("Fix authentication bug")
# Shows: ◐ Fixing authentication bug
```

### complete(content)

Mark a task as completed.

```python
todo.complete("Fix authentication bug")
# Shows: ● Fix authentication bug
```

### remove(content)

Remove a task from the list.

```python
todo.remove("Update docs")
```

### list()

Get all todos as text.

```python
print(todo.list())
# ○ Fix authentication bug
# ◐ Running tests
# ● Update docs
```

### update(todos)

Replace entire todo list (for bulk updates).

```python
todo.update([
    {"content": "Step 1", "status": "completed", "active_form": "Doing step 1"},
    {"content": "Step 2", "status": "in_progress", "active_form": "Doing step 2"},
    {"content": "Step 3", "status": "pending", "active_form": "Doing step 3"},
])
```

### clear()

Clear all todos.

```python
todo.clear()
```

## Task States

| Icon | Status | Description |
|------|--------|-------------|
| ○ | pending | Not yet started |
| ◐ | in_progress | Currently working on |
| ● | completed | Finished |

## Visual Display

When tasks change, TodoList shows a panel:

```
╭─── Tasks (1/3) ───────────────────────────────╮
│ ● Fix authentication bug                       │
│ ◐ Running tests                                │
│ ○ Update docs                                  │
╰────────────────────────────────────────────────╯
```

## Properties

### progress

Get completion percentage (0.0 to 1.0).

```python
print(todo.progress)  # 0.33 (1 of 3 completed)
```

### current_task

Get the currently in_progress task.

```python
print(todo.current_task)  # "Running tests"
```

## Use with Agent

```python
from connectonion import Agent, TodoList

todo = TodoList()
agent = Agent("worker", tools=[todo])

agent.input("""
Implement user authentication:
1. Create User model
2. Add login endpoint
3. Add logout endpoint
4. Write tests
""")

# Agent will:
# 1. Add all tasks to todo list
# 2. Start each task before working on it
# 3. Complete each task when done
# 4. Show progress throughout
```

## Best Practices

### Task Naming

Use both forms:
- **content**: Imperative form ("Fix bug", "Run tests")
- **active_form**: Present continuous ("Fixing bug", "Running tests")

```python
todo.add("Fix authentication bug", "Fixing authentication bug")
#         ^-- content              ^-- active_form
```

### One In-Progress at a Time

Only one task should be in_progress. Complete current before starting next.

```python
todo.add("Task A", "Doing A")
todo.add("Task B", "Doing B")

todo.start("Task A")
todo.start("Task B")  # Error: Another task is in progress
todo.complete("Task A")
todo.start("Task B")  # Now works
```

### Mark Complete Immediately

Complete tasks as soon as done, don't batch:

```python
# Good
todo.complete("Step 1")
# ... do step 2 ...
todo.complete("Step 2")

# Bad - batching completions
# ... do all steps ...
todo.complete("Step 1")
todo.complete("Step 2")
todo.complete("Step 3")
```

## Example: Multi-Step Task

```python
from connectonion import Agent, TodoList, DiffWriter

todo = TodoList()
writer = DiffWriter()

agent = Agent(
    "developer",
    tools=[todo, writer],
    system_prompt="""
    You are a developer. For complex tasks:
    1. Break into steps using TodoList
    2. Start each step before working
    3. Complete each step when done
    """
)

agent.input("Create a REST API with user CRUD operations")

# Agent workflow:
# 1. todo.add("Create User model", "Creating User model")
# 2. todo.add("Add GET /users endpoint", "Adding GET endpoint")
# 3. todo.add("Add POST /users endpoint", "Adding POST endpoint")
# ...
# 4. todo.start("Create User model")
# 5. writer.write("models.py", "...")
# 6. todo.complete("Create User model")
# 7. todo.start("Add GET /users endpoint")
# ...
```

## Customizing

Need to modify TodoList's behavior? Copy the source to your project:

```bash
co copy todo_list
```

Then import from your local copy:

```python
# from connectonion import TodoList  # Before
from tools.todo_list import TodoList  # After - customize freely!
```
