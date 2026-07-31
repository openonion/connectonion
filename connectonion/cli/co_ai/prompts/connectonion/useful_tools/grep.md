# grep

Search file contents with a regular expression.

```python
grep(pattern: str, path: Optional[str] = None, file_pattern: Optional[str] = None,
     output_mode: Literal["files", "content", "count"] = "files",
     context_lines: int = 0, ignore_case: bool = False, max_results: int = 50) -> str
```

| `output_mode` | what you get |
|---|---|
| `files` (default) | the paths that matched — cheapest, and usually the next question is "read one" |
| `content` | the matching lines, with `context_lines` around each |
| `count` | how many matches per file |

## Use it for

Finding where a symbol is defined or used, checking whether something exists at
all, and measuring how widespread a pattern is before changing it.

## Do not use it for

Finding files by name — `glob` is direct. Reading a whole file: `content` mode
with a huge `max_results` is a worse `read_file`.

## Scoping

`file_pattern` narrows by name (`"*.py"`), `path` narrows by directory. Both
together are what keeps a search over a large repository fast and readable.
