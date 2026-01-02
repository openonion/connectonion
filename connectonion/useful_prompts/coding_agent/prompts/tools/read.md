# Tool: Read File

Read file contents before making any modifications.

## When to Use

- **Always** before modifying an existing file
- Understanding code patterns and conventions
- Checking what libraries/dependencies exist
- Understanding imports and surrounding code

## Capabilities

- Reads any file type (code, config, images, PDFs)
- Returns content with line numbers (1-indexed)
- Default: first 2000 lines
- Use `offset` and `limit` for large files

## Guidelines

- Read the file BEFORE suggesting any changes
- Look at imports to understand dependencies
- Check for existing patterns in the codebase
- Read related files to understand context

## Examples

<good-example>
# Before editing auth.py, read it first
read_file("src/auth.py")

# Check dependencies before adding imports
read_file("requirements.txt")
read_file("package.json")
</good-example>

<bad-example>
# Don't modify without reading first
write("src/auth.py", "new content")  # Never do this!
</bad-example>
