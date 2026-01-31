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
- Provide options when there are clear choices
- Include a default when one option is clearly better
- Don't ask multiple questions at once - focus on one decision

## Format

```python
ask_user(
    question="Which database should we use?",
    options=["PostgreSQL", "SQLite", "MySQL"],
    default="PostgreSQL"
)
```

## Examples

<good-example>
# Clear options with recommendation
ask_user(
    "Which auth method should I implement?",
    options=["JWT tokens", "Session cookies", "OAuth"],
    default="JWT tokens"
)

# Gathering specific info
ask_user("What should the API endpoint be called?")

# Yes/No confirmation
confirm("Should I proceed with deleting these files?", default=False)
</good-example>

<bad-example>
# Too vague
ask_user("What do you want?")

# Could find this in codebase
ask_user("What framework is this project using?")

# Multiple questions at once
ask_user("What database, auth method, and deployment target?")
</bad-example>
