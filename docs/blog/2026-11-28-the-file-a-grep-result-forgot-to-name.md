# The file a grep result forgot to name

A tool result came back like this:

```
.:
  1: alpha
  2: beta alpha
```

The search had been given one file, `a.py`, and found two matches in it. The result says `.`. Not the file's name, not its path — the relative path of a directory against itself. An agent reading that has the lines but not the file, and the only way to get the name back is to search again, or to guess from the call it just made.

The cause is one line. A single named file is used as its own search base, and the display path was `file.relative_to(base)`. For a directory walk that is right: `src/app.py` relative to `src` is `app.py`. For one file against itself it is `.`. The fix keeps the path the caller gave: if the base is a file, report that file.

The same function had a second way of making output ambiguous. With `context_lines` set, each match printed its own window of surrounding lines. Two matches a line apart printed the shared lines twice:

```
  > 1: alpha
    2: beta alpha
    3: gamma

    1: alpha
  > 2: beta alpha
    3: gamma
```

Line 1 shows up once as a match and once as context. To a reader — human or model — that looks like four hits in a three-line file, and counting them is the sort of thing a model gets wrong quietly. The windows are now merged before they are printed: a line appears once, and the `>` marker still says which lines actually matched. Windows that do not touch keep their blank-line separation, so unrelated matches still read as separate blocks.

Both bugs are the same bug in different clothes. The tool knew which file it read and which lines matched, and then threw that knowledge away while formatting. `grep`'s output is the model's whole view of the disk for that call; anything the formatter drops, the model has to reconstruct by searching again.

The tests pin both halves: a named file is reported by the path it was given, a relative one keeps its directory, a shared context line is printed once, and windows that are far apart still come out as separate blocks.
