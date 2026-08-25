# CLI Browser

Drive one real browser from the shell — call browser functions directly, or hand a task to the AI agent.

## Quick Start (60 seconds)

```bash
co browser go_to news.ycombinator.com    # opens a browser, navigates
co browser get_current_url               # → https://news.ycombinator.com/
co browser take_screenshot /tmp/shot.png # saves a PNG, prints the path
co browser close                         # done
```

The browser stays open **between commands**. Each `co browser ...` call drives the *same* window — your navigation, cookies, and logged-in session persist until you `close`.

## Why Use This

Two ways to use a browser from the CLI, and you pick per command:

- **Direct function call** — `co browser go_to x.com`. Deterministic, instant, free (no LLM). Great for scripting and exact steps you already know.
- **Natural language** — `co browser do "find the cheapest flight"`. The AI agent figures out the steps. Great when you don't want to spell them out.

Both drive the **same live browser**, so you can mix them: script the boring parts, let the agent handle the hard part.

```bash
co browser go_to myapp.com/login
co browser do "log me in and open the billing page"   # agent takes over the same window
co browser take_screenshot /tmp/billing.png           # back to a direct call
```

## How It Works

The first `co browser` command starts a small background **daemon** that owns one browser. Every later command connects to it over a local socket and drives that same browser. The daemon lives exactly as long as the browser:

```
co browser go_to x.com   ──► starts daemon ──► opens browser ─┐
co browser click "Login" ──────────────────► same browser    │  state persists
co browser screenshot    ──────────────────► same browser    │
co browser close         ──► browser closes ──► daemon exits ─┘
```

You never manage the daemon directly — the **first command starts it**, and `close` (or closing the window) stops it. There is no separate "start" step.

### How a command is dispatched

The first word is compared against the browser's function names:

| You type | What happens |
|----------|--------------|
| `co browser go_to x.com` | `go_to` **is** a function → runs it directly |
| `co browser do "..."` | `do` → hands the instruction to the AI agent |
| `co browser frobnicate` | matches nothing → `unknown command: frobnicate` (exit 1) |

> Quote natural-language instructions: `co browser do "click the blue button"`. A bare word that happens to be a function name (like `click`) is treated as a direct call, not language.

## Discovering Functions

The CLI describes itself — run `help` to list every callable function with its arguments and a one-line summary (no browser is launched):

```bash
co browser help
```

```
Functions:
  go_to(url) — Navigate to a URL.
  take_screenshot(path=None, full_page=False) — Take a screenshot of the current page...
  click(description) — Click on an element using natural language description.
  get_links_from_page(domain_filter='') — Extract all unique links from the current page...
  ...
```

This is the fastest way — for a person or an AI agent — to find the exact function name and arguments before calling it.

## Common Functions

Any function listed by `co browser help` is callable. The ones you'll reach for most:

```bash
co browser go_to <url>                     # navigate
co browser get_current_url                 # print the current URL
co browser get_text                        # print visible page text
co browser take_screenshot /tmp/shot.png [--full-page]
co browser click "<description or selector>"
co browser type_text_by_selector <css> "<text>"
co browser fill_text_by_selector <css> --stdin < secret.txt  # replace controlled input; secret stays out of argv
co browser get_focused_element             # bounded JSON; password values are redacted
co browser keyboard_press Meta+a           # refused unless focus is editable
co browser get_links_from_page             # one link per line
co browser scroll                          # scroll the main content
co browser close                           # close browser, stop daemon
```

Arguments are plain strings; flags like `--full-page` and `--index=2` map to the function's parameters. For `fill_text_by_selector`, `type_text_by_selector`, and `keyboard_type`, a final `--stdin` reads the text from redirected standard input so passwords and one-run codes do not appear in process arguments. Prefer `fill_text_by_selector` when replacing a controlled framework input; use `type_text_by_selector` when appending human-shaped keystrokes is required.

Before replacing focused text with a keyboard shortcut, inspect the target:

```bash
co browser get_focused_element
co browser keyboard_press Meta+a       # macOS
co browser keyboard_press Control+a    # Windows/Linux
co browser keyboard_press Backspace
```

`get_focused_element` follows focus into open shadow roots and reports whether
the target is editable. Its value preview is bounded, and password values are
always redacted. `keyboard_press` refuses select-all, Backspace, and Delete when
focus is outside an editable input, textarea, or contenteditable element. For a
deliberate page-level shortcut, acknowledge the risk explicitly with
`--allow-non-editable`.

Focus inspection is scoped to the top-level document and open shadow roots. If
focus is inside an iframe, the result describes the iframe itself and treats it
as non-editable; closed shadow roots cannot be inspected. These cases fail safe:
target the field by selector, or use the explicit override only after verifying
the frame and intended page-level action.

> **Use absolute paths for files.** The daemon resolves relative paths against *its own* working directory (where it was first started), not the directory you run each command from. `take_screenshot /tmp/shot.png` is predictable; a bare `shot.png` lands in the daemon's `.tmp/` folder.

## Screenshots

`take_screenshot` writes a PNG and prints **where it saved** — not the image data:

```bash
$ co browser take_screenshot /tmp/shot.png
Screenshot saved to: /tmp/shot.png
```

Omit the path and it auto-names the file under the daemon's `.tmp/` folder:

```bash
$ co browser take_screenshot
Screenshot saved to: /Users/you/project/.tmp/step_20260630_142927.png
```

Add `--full-page` to capture the entire scrollable height instead of just the viewport.

> **Why a path, not the image?** The underlying `take_screenshot()` function returns a base64 data URL — that's what the AI agent "sees" when it drives the browser with `do`. A direct CLI call deliberately prints the **file path** instead, so `co browser take_screenshot` never floods your terminal with a screenful of base64. Open or pipe the saved file when you want the actual image.

## Scripting

Output is clean stdout, errors go to stderr, and the exit code is `0` on success / `1` on failure — so commands compose like any Unix tool:

```bash
# Capture a value
url=$(co browser get_current_url)

# Pipe list output (one item per line)
co browser get_links_from_page | grep github | wc -l

# Fail-fast in a script
co browser go_to "$DEPLOY_URL" && co browser take_screenshot /tmp/deployed.png
```

## Sharing the Browser With Other Agents

One machine, one browser, often several agents. They stay out of each other's
way through named tabs — and by saying how long they expect to need one.

```bash
co browser tab open scrape --who alice --for "scrape pricing" --needs 10m
co browser -t scrape go_to example.com/pricing    # -t on EVERY command
co browser -t scrape get_text
co browser tab close scrape                        # release when done
```

`--needs` takes `30s`, `10m`, or `2h`. It is not a lock — it is the estimate
other agents read before touching your tab:

```bash
co browser tab ls
```

```
Tabs (2):
   [scrape] https://example.com/pricing  who=alice  purpose='scrape pricing'  open 3m
      last: "get_text" · 12s ago
      owner expects to finish by 14:20 (7m left) — leave it alone until then
   [stale] https://...  who=bob  purpose='check stock'  open 2h
      owner expected to finish by 12:30 (1h ago) — free for another agent to close
```

**Inside the window, leave it alone** — open your own tab instead. **Once it has
passed, the tab is free**, and closing it is a courtesy: an estimate that ran out
with the tab still open means that agent crashed, not that it is still working.

A tab opened without `--needs` frees up after ~2 minutes of silence, which is
wrong whenever you are waiting on a slow page or a human. Say the number.

Named tabs are also the concurrency boundary. The daemon owns one asyncio browser
runtime: two operations aimed at `scrape` queue behind each other, while `scrape`
and `inbox` may run at the same time. A registry lock decides claim races before
either operation touches a page, so concurrency never means two agents silently
sharing one tab.

Set `CO_WHO` so your commands carry your identity:

```bash
export CO_WHO=alice
```

## Headless vs GUI

By default the browser is **visible** (a real Chrome window you can watch). Add `--headless` for scripts/CI:

```bash
co browser --headless go_to example.com    # no window
co browser go_to example.com               # visible window (default)
```

The mode is fixed when the daemon starts (the first command). To switch modes, `co browser close` first, then start again with the mode you want.

## Natural Language Agent

`do` runs the full AI browser agent on the live browser and prints its final answer:

```bash
co browser do "search for wireless headphones and list the top 3 prices"
```

This path uses managed keys — run `co auth` once if you see an authentication message.

## Installation

**None needed (1.2.1+).** The Patchright library ships with connectonion, and the first
page-driving command auto-installs a browser when none exists — a one-time download,
announced in your terminal, into your per-user directory (no admin rights). If a desktop
Google Chrome is installed at the standard location, it is detected and used instead,
with zero downloads.

Manual fallback (older versions, airgapped machines, or a failed auto-install):

```bash
python -m patchright install chromium   # per-user, never needs admin
python -m patchright install chrome     # branded Chrome: best stealth, system installer
```

## Sessions & Profile

- One async browser runtime per machine, backed by a persistent profile at `~/.co/browser_profile/` — so logins survive restarts.
- The daemon endpoint: a Unix socket under `$XDG_RUNTIME_DIR/co/browser.sock` on macOS/Linux, a per-user named pipe on Windows (native, 1.2.1+ — no WSL). Override with `$CO_BROWSER_SOCK`.
- Client work is bounded: 1 MiB request cap, 120-second read/reply deadlines,
  32 admitted connections, and eight blocking transport workers on Windows.
- On Windows, `co browser close` returns only after the serving daemon exits, so
  an immediate next command can safely start a fresh daemon.
- For an isolated automation run, set `$CO_BROWSER_PROFILE_DIR` to a dedicated absolute directory and `$CO_BROWSER_SOCK` to a dedicated socket. Keep the real `$HOME`; replacing it can break OS-backed browser behavior and credentials.

## Error Messages

Errors print to **stderr** and exit with code `1`. Each one tells you the next step — handy when an AI agent is driving the CLI and needs to self-correct.

**Unknown function**
```bash
$ co browser frobnicate
unknown command: frobnicate
Run 'co browser help' to list functions, or 'co browser do "<instruction>"' for natural language.
```
The first word didn't match any browser function. List them with `co browser help`, or use `do` to describe the task in plain English.

**Wrong arguments**
```bash
$ co browser go_to
TypeError: BrowserAutomation.go_to() missing 1 required positional argument: 'url'
usage: go_to(url)
```
The function exists but the arguments don't fit. The `usage:` line shows the exact signature — pass the missing argument: `co browser go_to example.com`.

**Authentication required** (only for `do`)
```bash
$ co browser do "find the price"
Browser agent requires authentication. Run: co auth
```
The natural-language agent uses managed keys. Run `co auth` once. Direct function calls don't need this.

**Patchright not installed**
```bash
Browser tools not installed. Run: pip install patchright && patchright install chrome
```

## Troubleshooting

```bash
# Nothing happens / stuck browser → close and start fresh
co browser close

# See what the agent/daemon is doing
cat ~/.co/browser.log

# Authentication needed (only for `do`)
co auth
```

## See Also

- [`co auth`](auth.md) — managed keys for the `do` agent
- [Browser tools library](../useful_tools/browser_tools.md) — `BrowserAutomation` used in your own agents
- [Templates](../templates/README.md) — scaffold a project whose agent drives this CLI
