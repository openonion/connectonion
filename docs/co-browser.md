# `co browser`

Drive **one persistent, logged-in browser from the shell** — and let several AI agents share it without stepping on each other's pages.

## Quick Start (60 seconds)

```bash
co browser go_to https://news.ycombinator.com   # opens a real browser, navigates
co browser get_text                              # dumps the page text
co browser do "click the top story and summarize it"   # let the AI agent do it
co browser close                                 # shut the browser down
```

The browser stays open between commands — one shared session — so cookies and
logins persist from one command to the next until you `close`. The first run
opens a window you can log into once; every later run reuses that session.

Two ways to drive it:

- **Direct functions** (deterministic): `go_to`, `get_text`, `click_element_by_selector`,
  `take_screenshot`, `type_text_by_selector`, … — run `co browser help` for the full list.
- **`do "<instruction>"`** (natural language): an AI agent operates the same live
  browser and figures out the steps itself.

Output contract: **stdout = data, stderr = errors.** Exit code is `0` on success.

## Why Use This

An automation script that spins up a fresh headless browser every run throws away
your logins and pays the launch cost each time. `co browser` keeps **one real
browser alive** behind a small daemon, so:

- You log into a site **once**; subsequent commands are already authenticated.
- A shell script (or an AI agent) can issue many quick commands against the same page.
- Multiple agents can work in the same browser at the same time — each in its own tab.

## One Task = One Tab

The browser has **tabs**, and the rule is simple: **one task uses one tab.**

Solo use needs no ceremony at all — bare commands run on the shared **`main`** tab:

```bash
co browser go_to example.com     # runs on 'main'
co browser get_text              # still 'main'
```

Running a distinct task (or a second agent)? Give it its own tab:

```bash
NAME=$(co browser tab open --who alice --for "scrape pricing")   # prints the tab name
co browser -t "$NAME" go_to https://example.com/pricing          # -t targets that tab
co browser -t "$NAME" do "extract every plan and its monthly price"
co browser tab close "$NAME"                                     # release it when done
```

`-t <tab>` uses the exact same grammar for direct functions **and** `do`. A bare
command (no `-t`) always means the `main` tab.

## Several Agents, One Browser (contention)

When two agents share the browser, the daemon makes sure they never silently drive
the **same page**. If a second agent runs a bare command while another is mid-task
on `main`, it fails loudly and is told exactly what to do instead:

```
$ co browser go_to other.com
tab 'main' is in use by alice — last: go_to example.com · 4s ago

You are a second agent on this browser. Two agents cannot share one tab.
Run your task in your own tab — three commands:
  1. co browser tab open <name> --who <your-name> --for "<what you are doing>"
  2. co browser -t <name> <verb> [args]      # add -t <name> to EVERY command, including do
  3. co browser tab close <name>             # when your task is done

see who owns what:  co browser tab ls
```

This error **is the documentation** — an agent that has never read these docs
learns the whole lifecycle from the message it gets on its first collision. The
same guard protects named tabs and refuses `tab close` of a tab another agent is
using.

A claim lasts ~2 minutes from the tab's last command; once it expires the tab is
free for anyone to take over (and the board shows the new occupant).

### The board

See who is running what, right now:

```bash
co browser tab ls
```

```
Tabs (2):
  *[main]   https://example.com          who=alice   purpose='shared main tab'
            last: get_text · 3s ago
   [scrape] (reserved — no page yet)     who=bob     purpose='scrape pricing'
```

`tab ls --json` returns the same board as JSON for scripting.

### Identity

The daemon needs to know **who** you are to attribute tabs and enforce the guard:

- Set `CO_WHO=<name>` to name yourself (recommended for scripts).
- Claude Code sessions are identified automatically.
- An anonymous caller (no `CO_WHO`) can still use the browser, but gets no
  contention protection — so concurrent agents should always set `CO_WHO` or use
  named tabs.

```bash
export CO_WHO=alice        # once per shell/script — every command now carries it
co browser go_to example.com
```

Names may contain any character (spaces, quotes) — identity travels in a
structured envelope, never spliced into the command line.

## Exit Codes

`co browser` returns structured exit codes so an orchestrator can branch without
parsing prose:

| Code | Meaning |
|------|---------|
| `0`  | success |
| `1`  | the action failed (e.g. a selector matched nothing, a file to upload is missing, `run_page_script` found no script, `switch_page` has no such page), the command ran out of its 120-second deadline, the daemon is not answering, or it is busy at connection capacity |
| `2`  | usage error (bad flags, empty `-t`, `tab` misuse, wrong arguments for a function — the message shows its signature — or a `go_to` address that is not a web URL) |
| `3`  | nothing to act on: unknown tab (`-t` names a tab that was never `tab open`ed), or no browser is open yet — the message names the `go_to` that opens one |
| `4`  | tab busy (another agent is mid-task on that tab, or an earlier command on it is still running past this one's deadline) |
| `5`  | `do` cannot tell which account pays for its model, or has no credentials — run `co auth` |
| `6`  | the running daemon is pinned to a different engine than the one asked for — the message names the commands that work |

A selector that matches nothing is a failure for the functions that act on it
(`click_element_by_selector`, `type_text_by_selector`, `fill_text_by_selector`)
and for `get_element_text_by_selector`, which would otherwise print the error
sentence to stdout as if it were the element's text. `count_elements_by_selector`
answering `0 elements` is an answer, exit `0`. Functions that return page
content (`get_text`, `extract_*`, `run_page_script`, …) exit `0` whatever the
page says.

`go_to` refuses an address it cannot load before starting anything, with exit
`2`: a scheme other than `http`, `https`, `file`, `data`, `about` or `chrome`
(`javascript:`, `mailto:`, a typo like `htp://`), or text that is not a host
name (`"not a url"`). A bare host still gets a scheme, as always:
`example.com` → `https://example.com`, `localhost:8000` → `http://localhost:8000`.

## Command Reference

```
co browser [-t TAB] <function> [args]    run a browser function (bare = the shared 'main' tab)
co browser [-t TAB] do "<instruction>"   let the AI agent do it — same targeting grammar
co browser tab open [NAME] [--who <agent>] [--for "<purpose>"] [--needs 10m]   register a tab; prints its name
co browser tab ls [--json]               the board: every tab, who runs it, last command
co browser tab close <NAME>              release your tab when the task is done
co browser status                        browser state, stealth-driver health, last command, the board
co browser close                         close the browser and stop the daemon
co browser help                          list every browser function
co browser --headless <function>         run without a visible window (first command decides — see below)
```

### Everyday functions

`co browser help` prints the live list; these cover most sessions:

```bash
co browser go_to https://example.com/login       # navigate (https:// is assumed if omitted)
co browser get_text                              # the page's visible text
co browser get_links_from_page                   # every link, one per line
co browser take_screenshot                       # saves a PNG, prints its path
co browser click_element_by_selector "#submit"   # deterministic click by CSS selector
co browser type_text_by_selector "#email" "aaron@example.com"
co browser fill_text_by_selector "#invite" --stdin < invite.txt  # controlled input; keep secrets out of argv
co browser save_state auth.json                  # export cookies/localStorage (keep it secret!)
```

Function arguments follow the shell: positional args in order, options as
`--flag=value` or `--flag value` (e.g. `take_screenshot --full-page=true` or
`take_screenshot --full-page true`). A boolean flag alone (`--full-page`) means
true; a word after it that is not `true`/`false`/`yes`/`no`/`on`/`off`/`1`/`0`
stays positional, so `take_screenshot --full-page shot.png` still names the
file. Calling a function with the wrong arguments returns its usage line so a
script (or agent) can self-correct.

### Network: what the page sent, and a HAR of it

A page is two things: the DOM you can see, and the requests it made. The DOM
side is `get_text` / `save_page_context`; this is the other side. The surface is
the one [agent-browser](https://github.com/vercel-labs/agent-browser) uses, so
an agent that knows one knows the other; the tab name you already use with `-t`
says whose traffic you mean.

```bash
co browser -t shop network requests                          # what this tab has sent
co browser -t shop network requests --filter /api/ --type xhr,fetch --status 4xx
co browser -t shop network requests --method POST --json     # for a skill to read
co browser -t shop network request 7                         # one request, in full
co browser -t shop network request 7 --raw                   # with header values
co browser -t shop network clear                             # then one action, to isolate it
```

`requests` is the index — a header line, then method, status, kind, size,
duration, URL, newest last, id first so `cut -f1` feeds `request`. `--status`
takes `200`, `2xx` or `400-499`, and `--type` a comma list of Playwright's
resource types (`document`, `xhr`, `fetch`, `script`, `image`, …); a value that
is neither is an error, not an empty list, so a typo cannot read as "no
errors". `request <n>` opens one: request headers, request body, response
headers, response body; a request that never got a response says
`status=no response`.

To see what **one action** did, clear first:

```bash
co browser -t shop network clear
co browser -t shop click_element_by_selector "#search"
co browser -t shop network requests
```

Indexes are never reused after a clear, so an id you wrote down cannot come to
mean a different request later.

**A HAR records a task.** `requests` is for looking now; a HAR is a file — the
standard format Chrome DevTools and Charles import, and that Playwright's
`route_from_har()` replays with the site gone:

```bash
co browser -t shop network har start                  # text bodies embedded (default)
co browser -t shop network har start --content all    # every body, binary as base64
co browser -t shop network har start --content none   # metadata only
# ... do the task ...
co browser -t shop network har stop                   # ~/.co/browser/har/shop-<time>.har
co browser -t shop network har stop checkout.har --raw
```

The recording holds what the tab did between `start` and `stop`, and only that
tab: a request that finished before `start` stays out even though its body was
read after it. A second `start` is refused rather than silently throwing the
first recording away. The file is written owner-only (0600).

**Header values are shaped, not printed.** The consumer of this is usually a
skill, and a skill feeds an LLM, so a session cookie must not arrive in a prompt
by accident:

```
x-sign: <32 hex>
authorization: Bearer <48 chars>
set-cookie: <2 pairs, 28 bytes>
content-type: application/json
```

The shape is the reusable part — that an endpoint wants a 32-character hex
signature is the answer; the digits are just somebody's session. Headers that
let you rebuild the call (`content-type`, `origin`, `referer`, `user-agent`) are
printed whole. Add `--raw` for the values. A HAR follows the same rule: cookie
and header values are shaped in the file unless you stop it with `--raw`, and
then it is a live login — treat it like a password.

Outside a recording, bodies are read only for `xhr`, `fetch` and `document`
responses with a textual content type. Images, fonts, media and video segments
are listed — they are part of what the page did — but never downloaded twice,
which is what keeps this free on a page full of them. While a HAR records, its
`--content` widens that: `text` to every textual body (scripts and stylesheets
too), `all` to binary as well. A body over 64 KiB goes to a file under
`~/.co/browser_network/` and the record names it; the HAR embeds it whole.

The log is per tab, holds the last 500 requests, and goes away with the tab.

### Cookies

Cookies belong to the whole browser, not to one tab. The tab says which site
you mean: its current page decides the default scope, and `--all` widens to
every site.

```bash
co browser -t shop cookies                    # name, domain, path, expiry, flags, value (shaped)
co browser -t shop cookies --raw              # with the values
co browser -t shop cookies set theme dark     # on the tab's site; --domain D --path / to be explicit
co browser -t shop cookies clear              # this site only; `cookies clear --all` for everything
co browser -t shop cookies save               # ~/.co/browser/cookies/shop.json
co browser -t shop cookies load ~/.co/browser/cookies/shop.json
co browser cookies --all --json
```

A saved file is Playwright's `storage_state` shape, the same one `save_state`
writes and `BrowserAutomation(seed_state=...)` reads, and it is written 0600: it
is a live login. A tab with no site open is told to `go_to` one (or pass
`--all`) rather than being shown every cookie in the browser.

### `do` — natural language

`do` hands the same live browser to an AI agent that sees the page and works out
the steps itself — clicking, typing, scrolling, reading — until your instruction
is done:

```bash
co browser do "log into github with the saved credentials and open my notifications"
co browser -t scrape do "collect every plan name and monthly price into a list"
```

Describe the **end state** you want ("download the June invoice PDF"), not the
steps. `do` costs LLM calls and is slower than direct functions — use functions
for anything deterministic, `do` for judgment. The model loop runs in the CLI
process; each browser action takes one short daemon turn, so other tabs can make
progress while the model thinks. A command targeting the same claimed tab still
exits 4, preserving ownership instead of interleaving two tasks on one page.

## Visible or Headless

**The default is a visible window** — `co browser go_to example.com` opens real
Chrome on your screen, which is what you want for logging in once or watching an
agent work. Add `--headless` to run without a window:

```bash
co browser --headless go_to example.com
```

The choice is made by whichever command **starts the daemon** and sticks for the
daemon's lifetime — every later command reuses the same browser regardless of its
own flags (`co browser status` shows `headless=true/false`). A `--headless` that
reaches a daemon already running with a window says so on stderr rather than
being ignored. To switch modes, `co browser close` and let the next command
relaunch. Commands that only read a page (`get_current_url`, `get_text`,
`cookies`, …) never start a daemon: with nothing running they answer exit 3 at
once, so they cannot fix the mode before the `go_to` that was meant to.

## Best Practices

- **Solo work:** just use bare commands. Don't reach for `-t` until a second agent
  or a second concurrent task actually exists.
- **Say how long you need it:** `tab open ... --needs 10m` (`30s`/`10m`/`2h`).
  Other agents leave your tab alone until then, and the board shows them when
  you expect to be done. Without it, two minutes of silence is enough for
  someone else to take the tab — wrong when you are waiting on a slow page or
  a human.
- **Concurrent agents:** each `tab open`s once, adds `-t <name>` to **every**
  command (including `do`), and `tab close`s when finished. Set `CO_WHO`.
- **On an exit-4:** don't retry the same bare command — open your own tab (the error
  tells you how). Two agents on one page corrupt each other's navigation.
- **On an exit-3:** `tab open` the name first, then target it — a tab must be
  registered before `-t` can drive it.
- **Scripting:** `TAB=$(co browser tab open --for "job")` captures the tab name
  (that's the only thing `tab open` prints to stdout); branch on the exit code, and
  read `tab ls --json` to see the shared state. Its `active_requests` entries carry
  request id, caller, command, and start time while work is in flight; they disappear
  on success, failure, disconnect, or cancellation.

## How It Works

A small **daemon** owns the one browser and listens on a Unix socket (or an
authenticated named pipe on Windows); each
`co browser …` invocation is a short-lived client that sends one request and prints
the reply. Every terminal on the machine talks to the **same** daemon — there is
one browser, one board, no matter where you type. One asyncio runtime owns that
browser. Operations on the same tab are serialized; operations on independent
named tabs can progress together. Claim admission remains atomic, so two agents
racing for one tab still get one winner and one exit-4 refusal rather than
interleaved page mutations. It starts automatically on first use and exits when
you `close` it (or when the browser is no longer usable).

The daemon records its pid next to the socket, so a daemon that is merely **busy**
(for example, its bounded connection capacity is full) is never mistaken for a
dead one: clients wait briefly and report capacity instead of spawning a rival
daemon over a live browser. Each request is capped at 1 MiB, reads and replies
have absolute 120-second deadlines, and at most 32 client tasks are admitted; a
command beyond that is answered at once with "browser daemon is busy at
connection capacity (32 commands in flight) — try again shortly" (exit 1).
`status`, `close`, `tab ls` and `tab close` are never answered "busy": eight
more connections are kept for them, because they are how you get out of a full
daemon.

The command itself has the same 120-second deadline (a function's own longer
`--timeout` adds itself plus 15 seconds). Past it the daemon cancels the
command, which frees its tab, and answers exit 1 naming what it was waiting on —
for `cookies` and `save_state`, Chrome's cookie store, which on macOS waits on a
Keychain prompt until someone answers it. A command queued behind a stuck one on
the same tab is answered exit 4 instead. A client that goes away (killed, or
Ctrl-C) takes its command with it: the daemon notices the closed connection,
cancels the command, and its `active_requests` entry leaves the board. A bare
`close` cancels every running command first, so it never waits behind one.

The client has deadlines too: it waits 30 seconds for `status` or `tab ls`,
and for anything else the daemon's own deadline above plus 10 seconds for the
answer to arrive (130 seconds, or a longer `--timeout` plus 25). A read —
`get_current_url`, `list_pages`, `cookies`, `save_state` and the other verbs
that never open a page — asks `status` on a second connection every 10 seconds
while it waits: a daemon that answers is busy and is waited on, one that does
not is frozen, and the read gives up as soon as `status` would. A daemon that
does not answer — stopped with `kill -STOP`, or wedged — is reported as not
answering (exit 1), with `co browser close` as the way out.

With no daemon running, those reads — and `status`, `tab ls` and `tab close` —
answer that no browser is open and start nothing. Before 1.8.8b12 `tab ls`
started a headed daemon to list no tabs, and a later `--headless` command was
ignored with a note.

After each reply the daemon checks that the browser is still alive — after the
connection has closed, so the check never holds a slot. The check is one round
trip to Chrome shared by everyone asking, with a 3-second deadline. Chrome
answers it by reading its cookie store, which on macOS can wait on a Keychain
prompt; no answer is read as "unknown", never as "dead", so a slow Chrome is not
torn down. `co browser status` has deadlines of its own and says which question
went unanswered instead of hanging.
Cancellation or disconnect clears that request's active audit lease without
erasing another task's tab ownership. Startup itself is race-proof: a kernel lock
makes two terminals' simultaneous first commands elect exactly one daemon — the
loser exits and its command is served by the winner.

### Restart the daemon after an upgrade or downgrade

Installing a new ConnectOnion package does not replace a browser daemon that is
already running. Before the first `co browser do` on the new version, stop the
old process cleanly:

```bash
co browser close
```

The next page command starts a daemon from the newly installed package. Browser
logins survive because they live in the persistent profile, not in the daemon.
This restart matters for the 1.7 responsiveness update: a new client can still
send ordinary actions to the previous daemon, but that daemon does not know the
new raw screenshot response used by the client-side model loop, so vision would
silently receive a saved-file message instead of image data. Do the same before
downgrading so an older client never talks to a newer daemon.

## Troubleshooting

- **"Where is my browser window?"** The default is a **visible** window; if
  `co browser status` says `headless=true`, some earlier command started the
  daemon with `--headless`. Run `co browser close`, then rerun without the flag.
- **"tab 'X' is in use by …" (exit 4)** — another agent is mid-task there. Open
  your own tab (the error shows the three commands). `co browser tab ls` says
  when its owner expects to finish; once that has passed the tab is free and
  closing it is a courtesy, since an estimate that ran out with the tab still
  open means that agent crashed rather than that it is still working. A tab
  opened without `--needs` frees up after ~2 minutes of silence.
- **"Chrome failed to start"** — usually running over ssh/cron without a desktop
  session (start from a logged-in Terminal, or use `--headless`), or a leftover
  Chrome still holds the profile. The full launch log is in `~/.co/browser.log`.
- **"browser daemon is busy at connection capacity"** — 32 commands are in
  flight (or all bounded Windows transport workers are occupied). Retry shortly;
  an unrelated slow browser action on another named tab no longer blocks yours.
- **`status` says "Chrome did not answer a liveness check"** — the browser is up
  but its cookie store is not answering; on macOS that is usually a Keychain
  prompt waiting behind another window. Answer it, or `co browser close` and
  start again (logins are kept).
- **"did not finish within 120s — it was waiting on Chrome's cookie store"** —
  the same Keychain prompt, met by `cookies` or `save_state`. The command was
  cancelled and its tab is free; answer the prompt and run it again.
- **"the browser daemon … is running but did not answer"** — the daemon itself
  is stopped or wedged. `co browser close` finishes it: when the daemon does not
  answer within 60 seconds, close stops its processes (daemon and Chrome) itself,
  removes the socket, `.pid` and `.lock` the daemon would have removed, and
  exits 1 to say it had to.
- **Nuclear option** — only if `co browser close` could not finish it. Stop this
  one daemon by the pid it recorded beside its socket (logins survive: they
  live in the profile, not the daemon):

  ```bash
  # Linux
  kill -9 "$(cat "${CO_BROWSER_SOCK:-/tmp/co-$USER/browser.sock}.pid")"
  # macOS
  kill -9 "$(cat "${CO_BROWSER_SOCK:-$(getconf DARWIN_USER_TEMP_DIR)co-$USER/browser.sock}.pid")"
  ```

  Not `pkill -f 'connectonion.cli.browser_agent[.]daemon'`: that stops every
  browser daemon you have, including isolated ones on their own
  `$CO_BROWSER_SOCK` that another script or agent is using.

- **State locations** — profile (cookies/logins): `~/.co/browser_profile/`
  (the paid Onion engine's: `~/.onionwright/profiles/<address>`), or
  `$CO_BROWSER_PROFILE_DIR` and `$CO_BROWSER_PROFILE_DIR/onion` for the paid
  engine when that is set, so an isolated run is isolated on every engine ·
  daemon log: `~/.co/browser.log` · socket: `/tmp/co-<user>/browser.sock` on
  Linux, `<per-user temp dir>/co-<user>/browser.sock` on macOS (the dir
  `getconf DARWIN_USER_TEMP_DIR` prints), plus `.pid`/`.lock` beside it;
  `$CO_BROWSER_SOCK` overrides. No session variable (`$XDG_RUNTIME_DIR`,
  `$TMPDIR`) moves it, so a desktop login, ssh, su and cron all reach the same
  daemon. A daemon an older version started at `$XDG_RUNTIME_DIR/co/`,
  `/run/user/<uid>/co/` or `$TMPDIR/co-<user>/` is still found and can be
  closed; the next one starts at the address above.

## Remote control

Everything here runs the browser on **this** machine. To drive the browser on a
**remote** agent, prefix the same command with `co call <address>`:

```bash
co browser take_screenshot                          # local
co call 0x3d40... co browser take_screenshot        # remote (same verb)
```

`co call` sends the command to the remote agent over an authenticated WebSocket;
it runs there against the remote's own browser daemon and the result (text or a
saved screenshot) comes back. Gated by the remote's `.co/host.yaml` whitelist —
`co browser <verb>` is allowed by default. See [cli/call.md](cli/call.md).

## See Also

- `co browser help` — the live list of every function you can call directly.
- [cli/call.md](cli/call.md) — `co call`, the remote twin of this command.
- The `co-ai` project template (`co create`), whose agent drives this CLI
  for building agents on top of the same browser automation.
