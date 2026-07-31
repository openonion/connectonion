# edit

Replace an exact string in a file.

```python
edit(file_path: str, old_string: str, new_string: str, replace_all: bool = False) -> str
```

`old_string` must appear in the file **exactly**, whitespace included, and by
default must appear **exactly once**. Both rules are deliberate: an edit that
matches loosely, or matches in three places when you meant one, is an edit you
cannot review.

| | |
|---|---|
| no match | the edit fails and says so — usually the file is not what you assumed |
| several matches | the edit fails unless `replace_all=True` |

## Use it for

Surgical changes to a file you have already read.

## Do not use it for

Creating a file, or rewriting most of one. Use `write`. Editing a file you have
not read: the match will fail on whitespace you did not know was there.

## Making a match unique

Include a line above or below the target rather than reaching for
`replace_all`. `replace_all` is for renaming something that genuinely occurs
everywhere.
