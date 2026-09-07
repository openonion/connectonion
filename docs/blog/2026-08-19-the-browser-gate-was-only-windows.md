# The Browser Gate Was Only Windows

*2026-08-19*

The browser command already had a substantial end-to-end check. It built a
wheel, installed it like a user, started a real browser, and drove a page on
Windows. Then a preview check was run on a Mac and the first result looked like
a product failure: the daemon could not bind its socket and the test hung while
waiting for it to listen. The traceback was `PermissionError: [Errno 1]
Operation not permitted`.

That failure turned out to be the managed test sandbox refusing all Unix-domain
socket binds, not a broken Mac implementation. Running the same page-driving
flow in a normal Mac process succeeded immediately. The uncomfortable part was
that we had no repository gate that would have caught a real packaging or
first-launch regression on macOS, so the environmental explanation could have
been mistaken for confidence.

## A passing unit test is not a browser session

The macOS path has different machinery. Windows uses a named pipe; macOS uses
a Unix-domain socket. Packaging also matters: an editable checkout can hide a
missing package entry point or browser dependency that a wheel exposes. We
needed a test that ran where the socket was allowed, while still making the
failure visible and reproducible in CI.

The new macOS gate therefore builds and installs the wheel, installs
Patchright Chromium into an isolated runner directory, writes a local HTML
page, and drives the public CLI through the complete lifecycle:

```text
co browser --headless go_to file://…
co browser status
co browser get_current_url
co browser close
```

The assertions check the daemon's open state and the actual URL, not merely a
zero exit code. A local page keeps the test deterministic and avoids turning a
release check into a test of an unrelated website.

## What the gate proves

This is a release gate for the macOS co-browser path, not a claim that every
part of the broader 1.8 remote-browser and licensed-engine roadmap has landed.
That distinction matters: evidence should describe the path that was actually
executed. The gate now makes failures actionable when a macOS wheel, browser
install, Unix socket, navigation, or shutdown regresses.

The same scenario was run locally on macOS before the workflow was published.
The CI job repeats it on a clean hosted runner, where it can protect future
preview builds instead of relying on a one-off developer machine.
