# Tool: Ask User

Ask the user questions to clarify requirements or get decisions.

## When to Use

- **Clarify ambiguous requirements** - "Which database should I use?"
- **Get user preference** between options
- **Confirm before important decisions**
- **Gather missing information**

## When NOT to Use

- Information you can find in the codebase
- Obvious decisions with clear best practices
- Questions you can answer by reading files

## Guidelines

- Ask **specific** questions, not vague ones
- **Always provide options** - the `options` parameter is required
- Include a recommended option first when one is clearly better
- Don't ask multiple questions at once - focus on one decision

## Format

```python
ask_user(
    question="Which database should we use?",
    options=["PostgreSQL (recommended)", "SQLite", "MySQL"]
)
```

## Examples

<good-example>
# Clear options with recommendation
ask_user(
    question="Which auth method should I implement?",
    options=["JWT tokens", "Session cookies", "OAuth"]
)

# Yes/No confirmation
ask_user(
    question="Should I proceed with deleting these files?",
    options=["Yes, delete them", "No, keep them"]
)

# Multiple choice
ask_user(
    question="Which features do you want?",
    options=["Auth", "Database", "API", "Tests"],
    multi_select=True
)
</good-example>

<bad-example>
# No options provided (options is required!)
ask_user("What do you want?")

# Could find this in codebase
ask_user("What framework is this project using?", options=["React", "Vue"])

# Multiple questions at once
ask_user("What database, auth method, and deployment target?", options=["A", "B"])
</bad-example>
