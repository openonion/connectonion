---
name: co-browser
description: Drive one persistent, logged-in browser from the shell with `co browser`. Use when the user asks to open a page, log into a site, scrape/extract page content, fill forms, upload files, take screenshots, or automate any browser task — solo or with multiple agents sharing the browser.
tools:
  - Bash(co browser *)
  - Bash(CO_WHO=*)
  - Bash(export CO_WHO=*)
  - Bash(timeout *)
  - Bash(grep *)
  - Bash(sed *)
  - Bash(tail *)
  - Bash(sort *)
  - Bash(sleep *)
  - Bash(pkill *)
  - read_file
---

# co browser Skill

Drive **one real browser** from the shell. The browser stays open between commands —
cookies and logins persist until `co browser close`. Every terminal on the machine
talks to the same daemon: one browser, one board, no matter where you type.

**Always read the output, not just the exit code.** A failed action (selector not
found, browser not open) often returns exit `0` with the error text on stdout —
never chain `co browser ... && next_step` as your only success check.

## Step 1: Identity — who are you?

The daemon attributes every tab to a caller and uses that identity to stop two
agents from silently driving the same page. **Set `CO_WHO` explicitly** — shell
state does not survive between your tool calls, so a lone `export` is lost.
Either prefix every command:

```bash
CO_WHO=alice co browser go_to example.com
```

or keep the export and the commands in the SAME shell invocation:

```bash
export CO_WHO=alice && co browser go_to example.com && co browser get_text
```

(Some environments — e.g. Claude Code background jobs — are auto-identified,
but setting `CO_WHO` is always safe and never worse.) An anonymous caller still
works but gets **no contention protection**.

## Step 2: Check the board, then claim a tab

**One task = one tab.** Before touching the browser, see what's already happening:

```bash
co browser status      # browser state, headless flag, last command, the board
co browser tab ls      # every tab: who owns it, purpose, last command (--json for scripting)
```

**Solo (nobody else on the board)** — bare commands run on the shared `main` tab, no ceremony:

```bash
co browser go_to example.com     # runs on 'main'
co browser get_text              # still 'main'
```

**Concurrent (another agent or a second parallel task exists)** — open your own tab
and add `-t <name>` to EVERY command, including `do`. Pick an explicit literal tab
name — a `NAME=$(...)` capture is lost between tool calls:

```bash
CO_WHO=alice co browser tab open scrape --for "scrape pricing"
CO_WHO=alice co browser -t scrape go_to example.com/pricing
CO_WHO=alice co browser -t scrape do "extract every plan and its monthly price"
CO_WHO=alice co browser tab close scrape       # release when done
```

When delegating browser work to subagents, write each subagent's tab name into its
prompt — parallel agents share the one logged-in browser through separate tabs.

## Step 3: Pick the right verb

Two ways to drive the browser — pick per command, mix freely:

**Direct functions** (deterministic, instant, free — no LLM). Use for every step you can spell out:

```bash
co browser go_to https://example.com/login        # https:// assumed if omitted
co browser get_text                               # visible page text
co browser get_links_from_page                    # every link, one per line
co browser take_screenshot /tmp/page.png          # saves a PNG, prints its path
co browser click_element_by_selector "button" --index=0 --text="Send message"
co browser type_text_by_selector "#email" "user@example.com"
co browser scroll                                 # scroll the page (scroll 3 = fewer steps)
co browser get_current_url
```

`co browser help` prints the live list of every function with its arguments —
trust it over any example here. Calling a function with wrong arguments returns
its usage line: self-correct from that.

**`do "<instruction>"`** (natural language — an AI agent sees the page and works out
the steps). Use for judgment, not for steps you already know:

```bash
co browser do "log in with the saved credentials and open my notifications"
```

Describe the **end state**, not the steps. A `do` is a full agent run — many LLM
calls, possibly minutes — and the daemon is busy for its whole duration, so other
commands queue behind it. **Never wrap `do` in `timeout`**: killing the client
does not stop the run, it only orphans it (you pay for an answer nobody reads).

For state checks, prefer the free text probes first (exit 0 = matched):

```bash
co browser get_current_url | grep "/feed"
```

Only when the state is visually ambiguous, fall back to a one-word `do` probe:

```bash
co browser do "Look at the current page. Reply EXACTLY one of: STATE: feed | STATE: login | STATE: error"
```

## Step 4: Verify with evidence

- **Routine checks are text checks**: `get_current_url` / `get_text` after
  navigation and clicks. Reserve screenshots for evidence gates.
- **Irreversible actions (submit, post, publish, pay) get the full gate**:
  screenshot before, act **exactly once**, screenshot after. Never click the same
  submit button twice — if the result is ambiguous, report uncertain state
  instead of retrying.
- Long pages: dump once and read locally instead of re-extracting per chunk:

  ```bash
  co browser get_text > /tmp/page.txt    # one daemon round-trip
  sed -n '1,200p' /tmp/page.txt
  ```

- To find stable selectors, save the DOM and grep it:

  ```bash
  co browser save_page_context li_composer
  grep -o 'aria-label="[^"]*"' ~/.co/browser_context/*li_composer*/page.html | sort -u
  ```

- Site-specific DOM logic belongs in skill-local JS run with an **absolute path**
  (the daemon resolves relative paths against its own cwd, not yours):

  ```bash
  co browser run_page_script /path/to/project/.co/skills/<skill>/scripts/extract-items.js
  ```

## Step 5: React to failures

Exit codes cover the daemon-level contract; the output text covers the action itself:

| Signal | Meaning | What to do |
|--------|---------|------------|
| exit `0`, clean output | success | continue |
| exit `0`, error text on stdout | the action failed softly (e.g. "No element found for selector") | read it, adjust selector or approach |
| exit `1` | the command raised (bad arguments print the usage line) | self-correct from the message |
| exit `2` | usage error (bad flags, empty `-t`, `tab` misuse) | fix the command syntax |
| exit `3` | unknown tab | `tab open` the name first, then target it |
| exit `4` | tab busy — another agent is mid-task there | do NOT retry the same command — the error prints the exact commands to run instead; follow them |

The exit-3/4 error messages ARE the documentation — they always carry the current
recovery steps, so trust them over this table. A crashed agent's tab claim
expires on its own; if a stale claim blocks you, open your own tab rather than
closing theirs.

## Logging in

The default is a **visible** window — exactly what you want for a first login.
Never automate credentials: open the login page, tell the user, then check with
short waits — one short check per tool call, not one long blocking loop (a long
loop hits the tool timeout, and every poll refreshes your claim on the tab,
locking other agents out for its whole duration):

```bash
co browser go_to https://site.com/login
# tell the user to log in in the visible window, then per check-in:
sleep 15 && co browser get_current_url | tail -1
```

Repeat the check a handful of times; if the URL is still the login page after
that, stop and ask the user instead of looping forever. Logins live in the profile (`~/.co/browser_profile/`),
not the daemon — they survive `close` and restarts. Log in once, stay logged in.

Headless: `co browser --headless go_to ...` — the mode is fixed by whichever
command **starts** the daemon (`status` shows `headless=true/false`). To switch:
`co browser close`, then relaunch.

## Scripting hygiene

- Wrap **direct functions** that might block in `timeout 60 ...`; never `timeout` a `do`.
- Take the data line with `tail -1` when output includes env banners.
- Batch related commands in one tool call; never spend a whole call on a bare wait.
- Uploads: try `upload_file_by_selector 'input[type="file"]' <path>` first; if the
  input is hidden behind a button, `upload_file_after_click_by_selector '<button selector>' <path>`.

## Troubleshooting

- **"Where is my window?"** — `co browser status` says `headless=true`? An earlier
  command started the daemon headless. `co browser close`, rerun without the flag.
- **"daemon is busy"** — a long `do` is holding the single-threaded daemon. Wait
  and retry; `co browser status` shows the last command once it frees up.
- **"Opening in existing browser session" / profile in use (shows a PID)** — a
  manually opened Chrome or stale daemon holds the profile; kill that PID, retry.
- **`TargetClosedError` after a crash** — the page died under the daemon; run
  `co browser open_browser` again before retrying the command.
- **"Chrome failed to start"** — usually ssh/cron without a desktop session (run
  from a logged-in Terminal, or use `--headless`). Full launch log: `~/.co/browser.log`.
- **Nuclear option** — kill the daemon and let the next command start fresh
  (logins survive in the profile):

  ```bash
  pkill -f connectonion.cli.browser_agent.daemon
  ```

## Done checklist

- [ ] Identity attached to every command (`CO_WHO=... co browser ...`)
- [ ] Board checked (`status` / `tab ls`) before claiming a tab
- [ ] Own tab used if any other agent/task shares the browser (`-t` on every command)
- [ ] Output text read on every command, not just exit codes
- [ ] Irreversible actions performed exactly once, with before/after screenshots
- [ ] Tab closed (`co browser tab close <name>`) when the task is done
- [ ] Browser left open for the next task unless the user asked to `close`
