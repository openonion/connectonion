# A deadline nobody enforced

A tester re-checking `co browser` on a Mac ran `co browser cookies --all`, a
command new in 1.8.8, and it never came back. That had a known cause. Chrome
on macOS keeps its cookie store behind the Keychain, and when the Keychain
wants a password it puts up a prompt and waits. The prompt can sit behind
another window for as long as nobody looks. Our previous release had already
taught the daemon's own liveness check not to wait on that prompt forever.

So the tester did what anyone does with a hung command: Ctrl-C, and try
something else. That was where it got worse.

The daemon did not notice the client leave. Fifteen minutes later
`tab ls --json` still listed the cookie read under `active_requests`, even
though our docs say an entry disappears when its client disconnects. The
daemon's open file descriptors kept growing. Every later command on the same
tab queued silently behind the stuck one, with no timeout and no exit 4. After
about thirty of those, the daemon answered every command "busy at connection
capacity … try again shortly". That included `status`, the thing you run to
find out what is wrong, and `close`, the thing you run to fix it.

The docs had promised "absolute 120-second deadlines" all along. When we went
looking for the code behind that sentence, it covered reading the request and
writing the reply. Nothing timed the part in between, which is where the
command actually runs. We had a deadline in the documentation and on the
socket, and not on the work.

## What a deadline has to do

Putting a timer on the command was the easy part. The daemon now runs each
command as a task and gives it 120 seconds, or a longer `--timeout` the
command asked for plus fifteen. The more useful question was what has to
happen when the timer fires, and there were three things.

First, the work has to be cancelled, not abandoned. An abandoned coroutine
keeps its tab lock, and the tab lock is what made every later command on that
tab hang. Cancelling it runs its `finally` blocks, which release the lock and
remove its entry from the board.

Second, the answer has to say what the command was waiting on. "Timed out"
is true and tells nobody what to do. `cookies` and `save_state` now say they
were waiting on Chrome's cookie store, that on macOS it waits on a Keychain
prompt, and to look behind other windows. A command that timed out because it
was queued behind a stuck one on the same tab gets exit 4 and the name of the
command it was stuck behind, because that command is the real problem.

Third, the person answering the Keychain prompt should not have to wait two
minutes to find out it worked. So the daemon also watches the connection. An
OIP client sends nothing between its command and the reply, and it never
half-closes. If the socket reaches EOF while the command runs, the client is
gone, and the daemon cancels the command then instead of when the timer runs
out.

## The way out has to stay open

The capacity limit was right to exist and wrong about who it applied to. Now
`status`, `close`, `tab ls` and `tab close` get eight connections of their
own. `close` also used to wait for every running command to finish before it
tore anything down. It now cancels them first. A frozen daemon, which we
tested with `kill -STOP`, is the client's job. `status` now gives up after 30
seconds, other commands after 150, and the message names `co browser close`,
which already knew how to stop a daemon that does not answer.

The same tester had a list of smaller problems, and most of them were one
mistake. `run_page_script missing.js`, `switch_page 99` and an upload with no
file input all exited 0. The raw exception names they printed
(`TimeoutError: Page.goto: …`, `TypeError: AsyncBrowserCore.get_text() …`)
described the driver, not the command the user had typed. A wrong-argument
call is now a usage error that shows the signature. Asking whether a page is
open no longer starts a headed daemon that a later `--headless` would silently
ignore.

## The lesson

A deadline in the docs is a claim about the code, and ours did not match it.
The part of the command that could hang for hours was the part nothing timed.
When you write "every request is bounded", find the line of code that makes
it true, and check that it covers the slow part and not only the I/O around
it. Then check the commands people run when things are already stuck.
`status` and `close` are exactly the ones a capacity limit must never refuse.
