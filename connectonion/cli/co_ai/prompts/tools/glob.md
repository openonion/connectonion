# Tool: Glob

Fast file pattern matching for finding files by name.

## When to Use

- Find files by name pattern: `**/*.py`, `src/**/*.ts`
- Locate specific file types across directories
- Quick file discovery before reading

## When NOT to Use

- Searching file **contents** → use `grep` instead
- Reading file contents → use `read_file` instead
- Complex regex patterns → use `grep` instead

## Pattern Syntax

| Pattern | Matches |
|---------|---------|
| `*.py` | Python files in current dir |
| `**/*.py` | Python files in all subdirs |
| `src/**/*.ts` | TypeScript files under src/ |
| `test_*.py` | Files starting with test_ |
| `*.{js,ts}` | JS or TS files |

## Guidelines

- Returns file paths sorted by modification time (newest first)
- Use for broad file discovery, then `read_file` for specific content
- Prefer over bash `find` command

## Examples

<good-example>
# Find all Python files
glob("**/*.py")

# Find test files
glob("**/test_*.py")

# Find config files
glob("**/*.{json,yaml,toml}")
</good-example>

<bad-example>
# Wrong: searching for content
glob("import pandas")  # Use grep instead

# Wrong: too broad
glob("**/*")  # Be more specific
</bad-example>
