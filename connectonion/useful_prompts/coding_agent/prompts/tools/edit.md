# Tool: Edit

Perform exact string replacements in existing files.

## When to Use

- Modifying existing files
- Changing specific code sections
- Renaming variables or functions
- Updating configuration values

## When NOT to Use

- Creating new files → use `write` instead
- Replacing entire file contents → use `write` instead
- Reading files → use `read` first

## CRITICAL: Read Before Edit

**You MUST read a file before editing it.** This is a blocking requirement.

The Edit tool will fail if you haven't read the file first. Always:
1. Read the file with `read`
2. Understand the content and structure
3. Then use `edit` for modifications

## How It Works

The Edit tool performs **exact string replacement**:
- `old_string`: The exact text to find (must be unique in file)
- `new_string`: The replacement text
- `replace_all`: Set to `true` to replace all occurrences (useful for renaming)

## Guidelines

### Preserve Indentation
Copy the exact indentation from the Read output. The Read tool shows content with line numbers like:
```
    42→    def my_function():
    43→        return True
```
Everything AFTER the `→` is the actual file content. Match that indentation exactly.

### Never Include Line Numbers
The line number prefix (e.g., `    42→`) is NOT part of the file. Never include it in `old_string` or `new_string`.

### Make old_string Unique
If `old_string` appears multiple times, the edit will fail. Include enough surrounding context to make it unique:

<bad-example>
old_string: "return True"  # Too common, might match multiple places
</bad-example>

<good-example>
old_string: "def validate_user():\n    return True"  # Unique context
</good-example>

### Use replace_all for Renaming
When renaming a variable or function across a file:
```
old_string: "oldName"
new_string: "newName"
replace_all: true
```

### Prefer Edit Over Write
Always prefer editing existing files over creating new ones. Small, targeted changes are safer than full file rewrites.

## Examples

<good-example>
# Read file first
[read file.py]

# Then edit with exact match
old_string: "def old_function():\n    pass"
new_string: "def new_function():\n    return 42"
</good-example>

<bad-example>
# Editing without reading first - WILL FAIL
[edit file.py without reading]

# Including line numbers - WRONG
old_string: "   42→    def my_func():"

# Changing indentation - breaks the code
old_string: "    return True"
new_string: "return True"  # Lost indentation
</bad-example>
