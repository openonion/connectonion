# A text file that looked binary

A note exported on Windows arrives with a `.txt` extension and looks, in every
editor, like a note. The agent calls `read_file` on it and gets:

```
Error: 'notes.txt' looks like a binary file with an unsupported extension ('.txt'), not text.
```

The file is text. It is UTF-16, which on Windows is what `Out-File`, `>` and a
good number of export buttons produce by default. UTF-16 stores an ASCII letter
as two bytes with a zero in one of them, so the first few thousand bytes of any
English UTF-16 document are roughly half `\x00`. The tool's binary check is "does
this contain NUL bytes", and it ran before anything looked at the encoding.

## The BOM is not a guess

The reason the tool only tries UTF-8 and GB18030 is sound: short snippets are
easy to misdetect, and guessing wrong turns readable text into mojibake. But a
byte-order mark is not a guess. `FF FE` at the start of a file is the file
telling you what it is, and a decoder that ignores it while applying a heuristic
is doing the harder thing for a worse result.

So the check order is now: BOM first, NUL bytes second.

```python
for bom, encoding in _BOMS:
    if data.startswith(bom):
        return data.decode(encoding, errors="replace")
```

`_BOMS` is ordered longest-first, because UTF-32LE begins with the two bytes of
the UTF-16LE mark; checking the short one first would decode half a UTF-32 file
as UTF-16. UTF-8 keeps its own mark (`EF BB BF`), which is now stripped
explicitly rather than as a side effect of the detector.

The NUL check still runs for everything without a mark, so a real binary renamed
to `.txt` is rejected exactly as before.

## What was measured

| bytes | before | after |
| --- | --- | --- |
| `"hello\n".encode("utf-16")` | `Error: ... binary file` | `hello` |
| `BOM + "name,count\n"` as UTF-16BE | `Error: ... binary file` | `name,count` |
| `"记录\n".encode("utf-32")` | `Error: ... binary file` | `记录` |
| `b"\x00\x01\x02binary"`, no BOM | `Error: ... binary file` | `Error: ... binary file` |

Five tests: three encodings that used to be rejected, a UTF-8 BOM that must not
become part of the text, and the binary case that must keep failing.

## What this does not fix

UTF-16 without a BOM is still rejected, and that is deliberate. Without the mark
there is no way to tell UTF-16LE from a binary blob by inspection, and guessing
would trade this error for silent mojibake — worse, because the agent would read
the garbage and act on it. Better to say "this looks binary" and let the caller
re-export with a BOM.
