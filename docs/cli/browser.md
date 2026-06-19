# CLI Browser

Drive one real browser from the shell — call browser functions directly, or hand a task to the AI agent.

## Quick Start (60 seconds)

```bash
co browser go_to news.ycombinator.com    # opens a browser, navigates
co browser get_current_url               # → https://news.ycombinator.com/
co browser take_screenshot /tmp/shot.png # saves a PNG
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
co browser take_screenshot billing.png                # back to a direct call
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

## Common Functions

Any method on the browser is callable. The ones you'll reach for most:

```bash
co browser go_to <url>                     # navigate
co browser get_current_url                 # print the current URL
co browser get_text                        # print visible page text
co browser take_screenshot /tmp/shot.png [--full-page]
co browser click "<description or selector>"
co browser type_text_by_selector <css> "<text>"
co browser get_links_from_page             # one link per line
co browser scroll                          # scroll the main content
co browser close                           # close browser, stop daemon
```

Arguments are plain strings; flags like `--full-page` and `--index=2` map to the function's parameters.

> **Use absolute paths for files.** The daemon resolves relative paths against *its own* working directory (where it was first started), not the directory you run each command from. `take_screenshot /tmp/shot.png` is predictable; a bare `shot.png` lands in the daemon's `.tmp/` folder.

## Scripting

Output is clean stdout, errors go to stderr, and the exit code is `0` on success / `1` on failure — so commands compose like any Unix tool:

```bash
# Capture a value
url=$(co browser get_current_url)

# Pipe list output (one item per line)
co browser get_links_from_page | grep github | wc -l

# Fail-fast in a script
co browser go_to "$DEPLOY_URL" && co browser take_screenshot deployed.png
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

The browser needs Playwright:

```bash
pip install playwright
playwright install chromium
```

## Sessions & Profile

- One browser per machine, backed by a persistent profile at `~/.co/browser_profile/` — so logins survive restarts.
- The daemon's socket lives under `$XDG_RUNTIME_DIR/co/browser.sock` (override with `$CO_BROWSER_SOCK`).

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
- [`browser` template](../templates/browser.md) — scaffold a browser agent project
