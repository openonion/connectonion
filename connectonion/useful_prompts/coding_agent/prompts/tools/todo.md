# Tool: Todo List

Track tasks and progress for complex multi-step work.

## When to Use

- Complex tasks with 3+ distinct steps
- User provides multiple tasks to complete
- Need to track progress on a large feature
- Breaking down a refactoring effort

## When NOT to Use

- Single, straightforward tasks
- Trivial operations (fix typo, add one line)
- Pure Q&A conversations

## Task States

- `pending` - Not yet started
- `in_progress` - Currently working on (only ONE at a time)
- `completed` - Finished successfully

## Guidelines

- Mark task `in_progress` BEFORE starting work
- Mark task `completed` IMMEDIATELY after finishing
- Only ONE task should be `in_progress` at any time
- Break complex tasks into smaller, actionable items

## Examples

<good-example>
User: "Add dark mode to the settings page and run tests"

1. ☐ Read existing settings page code
2. ☐ Add dark mode toggle component
3. ☐ Add dark mode state management
4. ☐ Update styles for dark theme
5. ☐ Run tests and fix any failures
</good-example>

<bad-example>
User: "Fix the typo in README"

# Don't use todo for trivial single tasks
# Just fix it directly
</bad-example>
