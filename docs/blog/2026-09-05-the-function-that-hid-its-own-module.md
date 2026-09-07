# The Function That Hid Its Own Module

The You.com tools landed on `main` this morning with fifteen passing tests.
Two hours later the Python 3.10 job on an unrelated docs pull request went
red with twelve failures, all in that new test file, all the same line:

```
AttributeError: <function youcom_search at 0x7f83...> does not have the attribute 'httpx'
```

The tests patch `connectonion.useful_tools.youcom_search.httpx`. Read as a
path, that names the `httpx` import inside the `youcom_search` module. But
the package's `__init__` also does `from .youcom_search import youcom_search`,
which rebinds the package attribute `youcom_search` from the submodule to the
function of the same name. From then on `connectonion.useful_tools.youcom_search`
means the function if you get there by attribute access, and the module if
you get there through `sys.modules`.

Which one you get depends on the interpreter. Python 3.11 changed
`unittest.mock` to resolve dotted targets with `pkgutil.resolve_name`, which
imports the module. Python 3.10 walks the path with `getattr` and stops on the
function. So the same test file passed on 3.11, 3.12 and 3.13 in CI, passed
on the contributor's machine, passed in the reviewer's 3.11 virtualenv, and
failed only on the one version nobody ran locally.

That last part is the actual lesson. This was a fork pull request, so its
workflow runs needed a maintainer's approval click that never happened; the
review substituted a local run. A local run on one Python version is not the
matrix. The fix is one line, `patch.object(importlib.import_module(...),
"httpx")`, which lands on the same object everywhere. The rule that comes out
of it is that a substitute for CI has to cover what CI covers, and this repo's
CI starts at 3.10.
