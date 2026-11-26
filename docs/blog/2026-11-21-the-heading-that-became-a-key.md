# The heading that became a key

The docs tell you to write structured markdown into a memory. Their own example
does it: a key called `alice-techcorp`, and under it a `## Contact Info` block
with the email address.

```python
memory.write_memory("alice-techcorp", """# Alice - TechCorp

## Contact Info
- Email: alice@techcorp.com
""")
```

The write reports success. Then `read_memory("alice-techcorp")` gives back
`# Alice - TechCorp` and nothing else, and `list_memories()` shows two memories
where one was written:

```
Stored Memories (2):
1. Contact Info (27 bytes)
2. alice-techcorp (18 bytes)
```

The single-file format uses `## <key>` as its delimiter, and the parser treated
every `## ` line as a new key — including the ones inside the content. The
memory was not lost so much as cut in half, with the lower half renamed after a
heading.

## What a key actually looks like

`write_memory()` has always sanitized keys: lowercase, alphanumerics, `-` and
`_`. `"Alice Notes!"` is stored as `alicenotes`. So a heading carrying a space or
a capital can only ever be content — no call to `write_memory()` could produce
it.

That is the whole rule the parser now applies. A `## ` line starts a section only
if its text is already a sanitized key; otherwise it stays with the content above
it. The sanitizer moved into a module-level `_sanitize_key()` so the writer, the
reader and the parser can share the same definition instead of three copies of
the same comprehension.

```python
def _is_section_key(text: str) -> bool:
    return bool(text) and _sanitize_key(text) == text
```

No format change: files on disk are untouched, and every file written by the old
code still parses the same way.

## What it does not fix

`## notes`, all lowercase with no spaces, is still indistinguishable from a key,
because it is a legal one. Making that unambiguous needs escaping on write, which
changes what a hand-edited file looks like — a decision for a separate change
rather than something to smuggle into this one.

The regression test writes the docs' own example and then checks all four
surfaces: `read_memory()` returns the content intact, `list_memories()` shows one
memory, the heading is not listed as a key, and `search_memory()` still finds
lines that sit under it.
