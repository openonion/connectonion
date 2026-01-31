# Tool: Todo List

Track tasks and progress for complex multi-step work. Helps users understand your progress.

## When to Use

Use this tool proactively when:
1. **Complex multi-step tasks** - 3 or more distinct steps
2. **User provides multiple tasks** - numbered or comma-separated list
3. **Non-trivial work** - requires careful planning
4. **After receiving new instructions** - capture requirements immediately
5. **When starting work** - mark as `in_progress` BEFORE beginning

## When NOT to Use

Skip this tool when:
1. Single, straightforward task
2. Trivial operations (fix typo, add one line)
3. Task can be completed in less than 3 trivial steps
4. Pure Q&A or informational requests

## Task Format (REQUIRED)

Each task MUST have two forms:
- **content**: Imperative form ("Run tests", "Fix the bug")
- **activeForm**: Present continuous ("Running tests", "Fixing the bug")

```json
{
  "content": "Run tests",
  "activeForm": "Running tests",
  "status": "pending"
}
```

## Task States

- `pending` - Not yet started
- `in_progress` - Currently working (exactly ONE at a time)
- `completed` - Finished successfully

## Strict Rules

1. **Exactly ONE task in_progress** at any time (not less, not more)
2. **Mark complete IMMEDIATELY** after finishing (don't batch)
3. **Only complete when FULLY done** - never if:
   - Tests are failing
   - Implementation is partial
   - Errors are unresolved
4. **If blocked**: Keep in_progress and create a new task for the blocker

## Examples: When to Use

<example>
User: "Add dark mode toggle and run tests when done"

Assistant creates todo list:
1. Read existing settings page code
2. Add dark mode toggle component
3. Add dark mode state management
4. Update styles for dark theme
5. Run tests and fix any failures

<reasoning>
Used todo list because:
1. Multi-step feature (UI, state, styling)
2. User explicitly requested tests afterward
3. Inferred tests need to pass as final step
</reasoning>
</example>

<example>
User: "Rename getCwd to getCurrentWorkingDirectory across the project"

Assistant first searches codebase, finds 15 instances in 8 files.
Then creates todo list with specific items for each file.

<reasoning>
Used todo list because:
1. First searched to understand scope
2. Found multiple occurrences across files
3. Todo ensures every instance is tracked
4. Prevents missing any occurrences
</reasoning>
</example>

<example>
User: "Implement user registration, product catalog, shopping cart, and checkout"

Assistant creates todo list breaking down each feature.

<reasoning>
Used todo list because:
1. User provided multiple complex features
2. Organizes large work into manageable tasks
3. Allows tracking progress across implementation
</reasoning>
</example>

## Examples: When NOT to Use

<example>
User: "How do I print 'Hello World' in Python?"

Assistant answers directly without todo list.

<reasoning>
Did NOT use todo list because:
- Single, trivial task
- No multiple steps to track
- Just informational
</reasoning>
</example>

<example>
User: "Fix the typo in README"

Assistant fixes it directly without todo list.

<reasoning>
Did NOT use todo list because:
- Single straightforward task
- One location in code
- No tracking needed
</reasoning>
</example>

<example>
User: "Run npm install"

Assistant runs command directly.

<reasoning>
Did NOT use todo list because:
- Single command execution
- Immediate results
- No multiple steps
</reasoning>
</example>
