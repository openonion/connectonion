# Tool: Grep

Search file contents using regex patterns.

## When to Use

- Search for code patterns: `def my_function`, `class MyClass`
- Find text across files
- Locate imports, function calls, variable usage
- Complex regex searches

## When NOT to Use

- Finding files by name → use `glob` instead
- Reading entire file → use `read_file` instead
- Simple filename matching → use `glob` instead

## Capabilities

- Full regex syntax support
- Filter by file type or glob pattern
- Multiple output modes:
  - `files_with_matches` (default) - just file paths
  - `content` - matching lines with context
  - `count` - match counts per file

## Guidelines

- Start broad, narrow down if needed
- Use with `-A`/`-B`/`-C` for context lines
- Prefer over bash `grep` or `rg` commands

## Examples

<good-example>
# Find function definition
grep("def process_data")

# Find class with context
grep("class UserAuth", output_mode="content", C=3)

# Find all imports of a module
grep("from requests import", type="py")

# Find TODO comments
grep("TODO|FIXME", glob="**/*.py")
</good-example>

<bad-example>
# Wrong: use glob for filename patterns
grep("*.py")  # Use glob instead

# Wrong: too broad, will match too much
grep("the")  # Be more specific
</bad-example>
