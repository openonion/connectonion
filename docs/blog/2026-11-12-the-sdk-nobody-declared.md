---
title: "The SDK nobody declared"
date: 2026-11-12
description: Feishu and Lark inboxes needed lark-oapi, and nothing installed it. It ships with connectonion now, and the message for a missing SDK reinstalls connectonion instead of guessing at a pip.
tags: [Inbox, Feishu, Dependencies]
---

# The SDK nobody declared

In October we moved a listening station to an office Mac while its owner was
across town. `co lark check` said the credentials were missing and pointed at
`co auth lark`. That command needed the Feishu SDK, which nothing had
installed. `pyproject.toml` did not mention it at all, and `check` stopped at
the first problem, so the second one only appeared after the first fix
failed (#2163).

The fix was written the same week, in a release pull request that also
carried an unrelated change to how `co auth lark` prints its link. The release
notes reached `main`; the dependency did not. For a month every fresh install
still lacked `lark-oapi`, and the documentation still opened Feishu setup with
`pip install lark-oapi`.

Landing it now raised a question the old branch never had to answer. Once
`lark-oapi` is a dependency, what does "the SDK is not installed" mean, and
what should co tell you to do? It can no longer mean you skipped a step. It
means the environment co runs in lost a package that came with it. The old
advice, `pip install lark-oapi`, is now the wrong answer: co installs into its
own uv tool environment, and a bare `pip` puts the package into whichever
Python comes first on the PATH. The message would send you to fix a different
interpreter, and `listen` would fail exactly as before.

So the message now says what is true and names a command that restores it:
the SDK ships with connectonion, and reinstalling this exact connectonion,
with `uv tool install --force` or with pip, brings it back. Pinning the
version matters. Without it, uv resolves the latest stable release, and
someone on a preview would quietly go back a release to fix a missing
package. `co auth feishu` and `listen` now share that one message instead of
keeping two copies of it.

We chose a dependency over an extra for the reason the issue gave: the SDK is
pure Python, and everything it needs but two small packages (pycryptodome
and requests-toolbelt) was already installed. WhatsApp's compiled library
stays an extra because nobody who only uses Feishu should pay for it. The
lock gained exactly three packages, and the security audit over every extra
is still clean. The tests that skipped when the SDK was
absent now run against the real dispatcher on every machine.
