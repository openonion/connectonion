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
tab 'main' is in use by alice — last: "go_to example.com" · 4s ago

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
            last: "get_text" · 3s ago
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

## Exit Codes

`co browser` returns structured exit codes so an orchestrator can branch without
parsing prose:

| Code | Meaning |
|------|---------|
| `0`  | success |
| `1`  | the action failed (e.g. selector not found) |
| `2`  | usage error (bad flags, empty `-t`) |
| `3`  | unknown tab (`-t` names a tab that was never `tab open`ed) |
| `4`  | tab busy (another agent is mid-task on that tab) |

## Command Reference

```
co browser [-t TAB] <function> [args]    run a browser function (bare = the shared 'main' tab)
co browser [-t TAB] do "<instruction>"   let the AI agent do it — same targeting grammar
co browser tab open [NAME] [--who <agent>] [--for "<purpose>"]   register a tab; prints its name
co browser tab ls [--json]               the board: every tab, who runs it, last command
co browser tab close <NAME>              release your tab when the task is done
co browser close                         close the browser and stop the daemon
co browser help                          list every browser function
```

Add `--headless` before the function to run without a visible window.

## Best Practices

- **Solo work:** just use bare commands. Don't reach for `-t` until a second agent
  or a second concurrent task actually exists.
- **Concurrent agents:** each `tab open`s once, adds `-t <name>` to **every**
  command (including `do`), and `tab close`s when finished. Set `CO_WHO`.
- **On an exit-4:** don't retry the same bare command — open your own tab (the error
  tells you how). Two agents on one page corrupt each other's navigation.
- **On an exit-3:** `tab open` the name first, then target it — a tab must be
  registered before `-t` can drive it.
- **Scripting:** `TAB=$(co browser tab open --for "job")` captures the tab name
  (that's the only thing `tab open` prints to stdout); branch on the exit code, and
  read `tab ls --json` to see the shared state.

## How It Works

A small **daemon** owns the one browser and listens on a Unix socket; each
`co browser …` invocation is a short-lived client that sends one request and prints
the reply. The daemon serializes commands, tracks per-tab ownership, and keeps the
browser alive between commands. It starts automatically on first use and exits when
you `close` it (or when the browser is no longer usable).

## See Also

- `co browser help` — the live list of every function you can call directly.
- The `browser` and `hosted-browser` project templates (`co create --template browser`)
  for building agents on top of the same browser automation.
