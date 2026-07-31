# glob

Find files by name pattern.

```python
glob(pattern: str, path: Optional[str] = None) -> str
```

```
glob("**/*.py")                    every Python file under the tree
glob("test_*.py", path="tests")    by name, in one directory
```

Results come back sorted by modification time, newest first — the files someone
has been working on are the ones you usually want.

## Use it for

"Where is the config file", "which test files exist", "what did this project
just change".

## Do not use it for

Searching inside files. That is `grep`. Reading one file whose path you already
know — just `read_file` it.
