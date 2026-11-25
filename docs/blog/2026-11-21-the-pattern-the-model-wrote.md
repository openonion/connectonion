# The pattern the model wrote

`Memory.search_memory()` takes a regex. The pattern rarely comes from a person
typing at a keyboard anymore — an agent writes it, usually after reading a
sentence like "find every note that mentions an email address", and usually it
is correct. When it is not, the tool raises.

```python
memory.search_memory("(unclosed")
# re.error: missing ), unterminated subpattern at position 0
```

That is the wrong shape for a failure at the tool boundary. Every other mistake
`Memory` can make — a missing key, an empty store, a key that sanitizes to
nothing — comes back as a sentence the model can read and act on. A stray
`re.error` leaves the tool call by the exception path instead, where the caller
gets a stack trace rather than something it can retry with a corrected pattern.
The module's own header said as much: *no exceptions raised (returns error
messages)*. The regex compile was the one place that did not hold.

## Where the guard belongs

Both storage modes compiled the pattern themselves, in `_search_single_file()`
and `_search_directory()`, each a few lines in. Guarding both meant two
identical `try` blocks and a third place for them to drift apart, so the compile
moved up into `search_memory()` and the two helpers now take the compiled
pattern along with the original string:

```python
try:
    compiled = re.compile(pattern)
except re.error as e:
    return f"Invalid regex pattern: {pattern}\n{e}"
```

The string is still passed down because the "No matches found for pattern: …"
message quotes what the caller actually asked for, not a compiled object.

## What the tests say

Three regression tests: one for the single-file path, two for directory mode —
the second of those runs a bad pattern and then a good one, to show the rejected
pattern leaves nothing behind. All three fail on `main` with `re.PatternError` and pass with the
change; the file goes from 16 to 19 passing.

The honest limit: the tests call `Memory` directly. I did not run a full agent
loop against a model to watch a malformed pattern arrive from a provider, so the
claim here is about the tool's return contract, not about how often models
actually produce a broken pattern. If this is wrong, it will be wrong at the
edge — a pattern that Pydantic's `re` accepts but that a user meant literally,
such as `search_memory("C++")`, which is still a regex and still means "one or
more C".
