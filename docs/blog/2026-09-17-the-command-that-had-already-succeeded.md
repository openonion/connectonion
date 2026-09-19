---
title: The command that had already succeeded
date: 2026-09-17
---

# The command that had already succeeded

On a clean macOS machine, this is the entire first-run experience of
`co whatsapp`:

```
$ pip install 'connectonion[whatsapp]'
Successfully installed neonize-0.4.3.post0 ...

$ co whatsapp listen
The WhatsApp library is not installed. Run: pip install 'connectonion[whatsapp]'
```

The library is installed. You can see it being installed, two lines up. Running
the suggested command again installs it again, successfully, and changes
nothing.

## Where the wrong sentence comes from

It comes from a shape that looks obviously correct:

```python
try:
    import neonize
except ImportError as exc:
    raise RuntimeError(SDK_MISSING) from exc
```

This is the standard optional-dependency guard, and it encodes an assumption it
never states: **that the only reason an import fails is that the package is
absent.** For a pure-Python package that is nearly true. neonize is not one.
It imports `python-magic`, which is a *binding* — a thin Python wrapper around
the system library `libmagic`. pip installs the binding. The library it binds
to comes from Homebrew, or apt, or dnf.

So the real error, several frames down, is:

```
ImportError: failed to find libmagic.  Check your installation
  File ".../neonize/client.py", line 21, in <module>
    import magic
  File ".../magic/loader.py", line 49, in load_lib
```

An `ImportError`, correctly caught — and then flattened into the one answer the
guard knows how to give.

## Why I did not just widen the message

The cheap fix is to append the system packages to `SDK_MISSING`: *not installed
— run pip install, and by the way you may also need libmagic*. One line, no new
branch, and the person in front of the failure does eventually read the word
libmagic. It is worse.

Someone who has genuinely not installed the extra now reads a paragraph about a
system library they do not need. Someone in the libmagic case reads that their
library is not installed, which is false, before reaching the sentence that is
true. Both people are handed a superset and asked to work out which half
applies to them. That is not an error message; it is a list of things that
might be wrong, which is what you write when you have not actually
distinguished the cases.

The cases are distinguishable, and cheaply. `ModuleNotFoundError` carries
`.name`:

```python
except ImportError as exc:
    if getattr(exc, "name", None) == "neonize":
        raise RuntimeError(SDK_MISSING) from exc
    raise RuntimeError(_sdk_will_not_load(exc)) from exc
```

`name == "neonize"` means the import of neonize itself found nothing — pip has
not run. Anything else means neonize is there and something underneath it is
not. Two different sentences, each addressed to someone who is actually in that
situation.

## The part I deliberately left dumb

`_sdk_will_not_load` recognises exactly one error by name. If the message
mentions libmagic, it names the package for `sys.platform` — `brew install
libmagic`, `apt install libmagic1`, `dnf install file-libs`. For anything else
it does this:

```
The WhatsApp library is installed but will not load: libz.so.1: cannot open
shared object file. Next: python -c 'import neonize' for the full traceback.
```

It repeats the error and hands over the traceback. No guess.

The temptation is to pattern-match more — "cannot open shared object file"
probably means a missing system library, so probably suggest the package
manager. But *probably* is how the original sentence got written. A message
that says "the WhatsApp library is not installed" was also a reasonable
inference from an ImportError, right up until it sent someone to rerun a
command they had just watched succeed. I would rather quote an error someone
can search than invent a fix I have not seen work.

## The rule underneath

A `try/except ImportError` is a claim about *why* an import failed, not just
that it did. Most of them are written as though absence were the only
possibility, and most of the time nobody notices, because most packages are
pure Python.

The cost is not evenly spread, either. This one landed on `co whatsapp listen`
— the first command anyone runs, the one that draws the QR code, the point
where a person is deciding whether this tool works at all. The worst place in
the product to answer a question nobody asked.

Three tests now hold it: one that the absent package still names the pip
command, one that the libmagic case names the system package and never says
`pip install`, and one that an error we do not recognise keeps its own text.
All three were red first, and the red output was the bug, verbatim: `assert
'apt install libmagic1' in "The WhatsApp library is not installed. Run: pip
install 'connectonion[whatsapp]'"`.
