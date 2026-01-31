# Tool: Shell

Execute terminal commands in a persistent shell session.

## When to Use

- Git operations: `git status`, `git add`, `git commit`, `git push`
- Package management: `npm install`, `pip install`, `cargo build`
- Running tests: `pytest`, `npm test`, `cargo test`
- Directory operations: `ls`, `mkdir`, `tree`
- Build commands: `npm run build`, `make`
- Any other shell command

## When NOT to Use

- Reading file contents → use `read_file` instead
- Writing files → use `write` instead
- Searching file contents → read files directly

## Guidelines

- Use absolute paths when possible to avoid `cd` confusion
- Chain dependent commands with `&&`: `git add . && git commit -m "msg"`
- Output is truncated at 30000 characters
- Default timeout: 2 minutes

### Path Quoting (REQUIRED)
Always quote paths with spaces using double quotes:
```bash
cd "/Users/name/My Documents"     # Correct
python "/path/with spaces/run.py" # Correct
cd /Users/name/My Documents       # WRONG - will fail
```

### Directory Verification
Before creating files/directories, verify the parent exists:
```bash
ls /foo           # Verify /foo exists
mkdir /foo/bar    # Now safe to create
```

### Parallel vs Sequential
- **Independent commands**: Call tool multiple times in parallel
- **Dependent commands**: Chain with `&&` in single call
```bash
# Sequential (dependent)
git add . && git commit -m "msg" && git push

# Parallel (independent) - use separate tool calls
[git status] [git diff] [git log]
```

## Examples

<good-example>
pytest /foo/bar/tests
git status
npm run build
cd "/path/with spaces" && ls
</good-example>

<bad-example>
cat file.txt                # Use read_file instead
echo "content" > file       # Use write instead
cd /foo && pytest           # Use absolute path instead
cd /path/with spaces        # Missing quotes - will fail
</bad-example>
