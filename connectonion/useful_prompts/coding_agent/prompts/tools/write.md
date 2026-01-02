# Tool: Write File

Write files with colorized diff display and user approval.

## Approval Flow

```
╭─── Changes to hello.py ────────────────────────╮
│ --- a/hello.py                                 │
│ +++ b/hello.py                                 │
│ @@ -1,2 +1,3 @@                                │
│  def hello():                                  │
│ -    pass                                      │
│ +    print("Hello, World!")                    │
╰────────────────────────────────────────────────╯

❯ 1 - Yes, apply this change
  2 - Yes to all (auto-approve for session)
  3 - No, and tell agent what to do instead
```

## Guidelines

- **Always read the file first** before writing
- Creates parent directories automatically if needed
- Returns byte count on success
- If rejected, user feedback is returned for you to retry

## Best Practices

- Match existing code style exactly
- Keep changes minimal and focused
- Don't add comments unless asked
- Don't refactor unrelated code

## Examples

<good-example>
# Read first, then write
content = read_file("src/utils.py")
# ... analyze content ...
write("src/utils.py", modified_content)
</good-example>

<bad-example>
# Writing without reading - don't do this
write("src/utils.py", completely_new_content)
</bad-example>
