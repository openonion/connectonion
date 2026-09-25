# The install line installed more than us

Two testers installed the 1.8.8b7 preview the way its release notes said to:

```
python -m pip install --upgrade --pre 'connectonion==1.8.8b7'
```

Everything local worked. Everything remote didn't. `connect(...).input()`
threw, a hosted agent answered "Agent error: Unable to run agent", and
`co outlook` fell over. The traceback said `httpx` has no attribute
`AsyncClient`. It did in every environment we had tested. In theirs it was
httpx 1.0.dev6.

We had pinned connectonion exactly and thought that was the whole story. But
`--pre` isn't about the package you name. It tells pip that any package may be
a pre-release, and pip then prefers the newest one it can find. In a scratch
venv, the same line with and without `--pre` gave three different
dependencies:

```
httpx      1.0.dev6   vs 0.28.1
pydantic   2.14.0b2   vs 2.13.5
lxml       7.0.0b1    vs 6.1.3
```

httpx 1.0 drops `HTTPError`, `AsyncClient` and `Timeout`, and our only
requirement was `httpx>=0.24.0`. So the preview broke first, but stable was
waiting its turn. The day httpx 1.0 is released, a plain
`pip install connectonion` would pick it up too.

The flag had never been needed. When a version specifier names a pre-release,
as `==1.8.8b7` does, pip allows that pre-release for that package and nothing
else. We checked against PyPI before believing it: `pip install --upgrade
'connectonion==1.8.8b7'` without `--pre` installs the beta, with httpx 0.28.1
beside it. So every install line we publish has dropped `--pre`, and the two
places the CLI prints one now print the running version pinned exactly. httpx
is capped below 1 and pydantic below 3. We capped only those two because we
know their next major breaks code we call. A cap added out of habit just stops
people installing us next to other packages. lxml comes in through
python-docx and python-pptx, so its cap is their call. A test holds the caps,
and another fails if an install line with `--pre` comes back.

While opening their environment, the testers found a second problem. The wheel
had grown to 9 MB, and `co init` had put 704 files into `.co/docs/`. Among
them was `docs/testing/`: 91 files of recorded wiki test runs, with about 245
absolute paths from the machine that ran them, like
`/Users/<maintainer>/projects/.worktree/...` and `.codex/sessions`. They were
in every project anyone created with 1.8.8b7.

Nobody had chosen to ship them. The pyproject mapped `docs/` into the package
with hatch's `force-include`, and a comment beside it said, correctly, that
force-include runs after the exclude rules, so nothing could be left out. That
was fine while `docs/` held only documentation. Then test evidence was
committed under `docs/`, and it shipped with everything else.

The mapping now uses `only-include` and `sources`. That puts the files in the
same place and still respects `exclude`. Test runs, acceptance records and
release screenshots stay out. The wheel dropped from 9.0 MB to 4.0 MB. The
list lives in `docs/.package-ignore`, which already existed and which nothing
had ever read. `co init` reads it now, so an editable install copies the same
docs a wheel does, and a unit test checks that the pyproject and the file list
the same paths. The paths already committed were rewritten to `~/`, because
the repository is public too.

We learned the same thing twice. The two lines looked like they meant "this
preview" and "our docs", and they meant more. What they did was only visible
from outside: in a fresh venv, or in a wheel someone had opened.
