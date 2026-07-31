# read_file

Read a file and hand back its contents. Dispatches on the extension, so one tool
covers text and images.

```python
read_file(path: str) -> str
```

| extension | what comes back |
|---|---|
| text, code, `.md`, `.csv`, `.json`, `.tex` | the file's text, as-is |
| `.png` `.jpg` `.jpeg` `.gif` `.webp` | the image enters your vision — after reading, you can see and describe it |

The image case is the one worth remembering: you do not get a path or a
description to reason about, you get the picture.

## Use it for

Anything you are about to change, quote, or answer questions about. Read before
you edit — `edit` matches on exact text, so a guess about what a file contains
becomes a failed edit.

## Do not use it for

Finding which file to read. That is `glob` (by name) or `grep` (by content).
