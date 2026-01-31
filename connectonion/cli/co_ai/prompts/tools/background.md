# Tool: Background Tasks

Run long-running commands in the background.

## When to Use

- **Long builds** - `npm run build`, `cargo build`
- **Dev servers** - `npm run dev`, `python manage.py runserver`
- **Watch modes** - `npm run watch`, `pytest --watch`
- **Any command** that runs indefinitely or takes >30 seconds

## When NOT to Use

- Quick commands (<30 seconds)
- Commands you need immediate results from
- One-off queries

## Available Functions

| Function | Purpose |
|----------|---------|
| `run_background(cmd)` | Start a background task, returns task_id |
| `task_output(task_id)` | Get output from running task |
| `kill_task(task_id)` | Stop a background task |

## Guidelines

- Save the task_id to check output later
- Use `task_output()` to monitor progress
- Remember to `kill_task()` when done with dev servers
- Background tasks persist until killed or session ends

## Examples

<good-example>
# Start dev server
task_id = run_background("npm run dev")

# Check output later
output = task_output(task_id)

# Stop when done
kill_task(task_id)

# Long build
task_id = run_background("cargo build --release")
# Continue with other work...
output = task_output(task_id, block=True)  # Wait for completion
</good-example>

<bad-example>
# Too quick - just run directly
run_background("ls")

# Need immediate result
run_background("git status")  # Just run normally
</bad-example>
