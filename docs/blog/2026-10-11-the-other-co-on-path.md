---
description: co ai's shell ran an older co from a pyenv shim, so the agent read help pages for a version that had no co linear. Its shell now runs the co that is running it, and nothing else of that install.
tags: [co ai, CLI]
---

# The other `co` on PATH

We were measuring whether `co ai` would use `co linear` for a question about
a Linear board. In one run it didn't, and for a reasonable-looking reason:
it ran `co commands`, read the list, found no `co linear`, and opened a
browser.

`co linear` was there in the install we had launched. But the agent's `bash`
tool doesn't run commands in that install. It runs them on the user's PATH,
and the first `co` on that PATH was a pyenv shim for 1.8.8, from before
`co linear` existed. The agent was hosted by one version and reading the
help of another. It drew the right conclusion from the wrong `co`.

This happens to anyone who upgrades with `pipx`, `uv tool` or a venv while an
older `co` still sits earlier on PATH. Nothing warns you. The agent just
seems unaware of commands you can see yourself.

## Not the whole bin directory

The fix the issue proposed was to put the running install's `bin/` first on
PATH. We almost did that, then saw the problem: that directory also holds
the install's `python` and `pip`. A coding agent in your project, with your
venv active, would suddenly run `python` from co's own environment, and
every `pip install` would land in co's venv. We'd be fixing one wrong binary
by introducing two.

So `co ai` now makes a small temporary directory holding one symlink, `co`,
pointing at the running install's script, and puts only that directory
first. `co` resolves to the right version. `python`, `pip` and everything
else resolve exactly as they did.

The test sets up two fake installs, each with its own `co` and `python`, and
puts the old one first on PATH. Through bash, it checks that `co` comes from
the running install and `python` still comes from the user's. On main, the
helper didn't exist. With an old shim first on PATH, `co --version` in the
agent's shell went from `co 1.8.8` to the running version.
