---
description: The handoff prompt's first install command was a global pip install, and on the Mac it failed only because that pip was broken. Step 1 now installs co with uv tool, pipx, or a private venv, in that order.
tags: [Handoff, Install]
---

# The install that only failed by luck

A `co handoff` arrives as a single prompt that the recipient pastes into
Codex or Claude Code. Step 1 makes sure `co` is installed. Until today its
first choice was:

```
pip install --upgrade "connectonion>=1.9.2b8"
```

While testing 1.9.2b8, we copied the prompt out of Gmail into a fresh Codex
on a Mac. Codex runs every command in a login shell, so that `pip` was the
person's own Python, the same one their other tools depend on. The install
failed, but only because `/usr/local/bin/pip` on that Mac happened to be
broken. Codex then fell back to the venv we had listed second, and the
handoff went through. It looked like it worked.

On a machine with a working pip, the same prompt would have upgraded
packages in the recipient's global Python. A handoff is meant for someone
who has never used co, maybe a colleague who doesn't write Python. For that
person, their global Python is the last place we should be installing
things, and they would not know what had changed or how to undo it.

## What step 1 says now

> If co is missing or older, install it in its own environment, never into
> the global Python: if uv is available, `uv tool install
> "connectonion>=X"`; otherwise, if pipx is available, `pipx install --force
> "connectonion>=X"`; otherwise `python3 -m venv ~/.co-venv &&
> ~/.co-venv/bin/pip install "connectonion>=X"`. Use that co for every co
> command below.

The version floor stays, because plain `connectonion` resolves to the last
stable release, which has no `co handoff accept`. The rule against running
`co init` when co is already new enough also stays.

We checked two details before writing the step. When the recipient already
has an older co from uv, `uv tool install` with a higher floor upgrades it by
itself. We tested this by installing 1.9.2b5 and then asking for
`>=1.9.2b8`. pipx works differently: it refuses a package it already has, so
the prompt passes `--force`.

## The run that counts

A unit test fixes the order of the three installs. A real agent then had to
follow the prompt. On Parrot, one of our always-on Linux machines, we made a
fresh HOME with nothing in it except a copy of the Codex login, and left `co`
off PATH. Since the branch is not on PyPI, we put a wheel of it in a local
folder that uv was told to check. Then we ran `codex exec` with the prompt
from a real `co handoff send`, with stdin closed.

Codex ran `co --version` and got "command not found". It found `uv`, ran
`uv tool install "connectonion>=1.9.2b8"`, and got the branch build. It then
ran `~/.local/bin/co init --yes` inside the fresh HOME, saved the brief, and
accepted. A few seconds later the Mac that sent the handoff printed:

```
Accepted by 0x87755e9626… (0x87755e9626@mail.openonion.ai) at 2026-10-10T22:47:15+00:00
```

Afterwards Parrot's own co, a uv tool install of 1.9.2b5, still had the same
version, the same file times and the same launcher hash as before the run.
Nothing outside the fresh HOME had changed.
