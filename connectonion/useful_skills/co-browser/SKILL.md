---
name: co-browser
description: Drive one persistent, logged-in browser from the shell with `co browser`. Use when the user asks to open a page, log into a site, scrape/extract page content, fill forms, upload files, take screenshots, or automate any browser task — solo or with multiple agents sharing the browser.
tools:
  - Bash(co browser *)
  - Bash(export *)
  - read_file
  - write_file
---

# co browser Skill

Drive **one real browser** from the shell. The browser stays open between commands —
cookies and logins persist until `co browser close`. Every terminal on the machine
talks to the same daemon: one browser, one board, no matter where you type.

Output contract: **stdout = data, stderr = errors.** Exit code `0` = success.

## Step 1: Identity — who are you?

The daemon attributes every tab to a caller and uses that identity to stop two
agents from silently driving the same page. Identity resolves in this order:

1. `CO_WHO` environment variable — set it explicitly in scripts and subagents:

   ```bash
   export CO_WHO=alice     # once per shell — every command now carries it
   ```

2. Claude Code sessions are identified automatically (as `claude-<session>`).
3. Anonymous — still works, but gets **no contention protection**.

Concurrent agents must always have an identity. Solo interactive use can skip this step.

## Step 2: Check the board, then claim a tab

**One task = one tab.** Before touching the browser, see what's already happening:

```bash
co browser status      # daemon health, headless flag, last command, the board
co browser tab ls      # every tab: who owns it, purpose, last command (--json for scripting)
```

**Solo (nobody else on the board)** — bare commands run on the shared `main` tab, no ceremony:

```bash
co browser go_to example.com     # runs on 'main'
co browser get_text              # still 'main'
```

**Concurrent (another agent or a second parallel task exists)** — open your own tab
with an owner and a purpose, then add `-t <name>` to EVERY command, including `do`:

```bash
NAME=$(co browser tab open --who "$CO_WHO" --for "scrape pricing")   # prints the tab name
co browser -t "$NAME" go_to example.com/pricing
co browser -t "$NAME" do "extract every plan and its monthly price"
co browser tab close "$NAME"                                         # release when done
```

When delegating browser work to subagents, give each subagent its own tab name in
its prompt — parallel agents share the one logged-in browser through separate tabs.

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
co browser scroll --direction=down
co browser get_current_url
```

`co browser help` prints the live list of every function with its arguments.
Calling one with wrong arguments returns its usage line — self-correct from that.

**`do "<instruction>"`** (natural language — an AI agent sees the page and works out
the steps). Use for judgment, not for steps you already know:

```bash
co browser do "log in with the saved credentials and open my notifications"
```

Describe the **end state**, not the steps. `do` costs LLM calls and is slower;
while it runs the daemon is busy and other commands queue behind it.

A cheap trick for state checks — force a one-word answer:

```bash
co browser do "Look at the current page. Reply EXACTLY one of: STATE: feed | STATE: login | STATE: error"
```

## Step 4: Verify with evidence

Screenshots are ground truth — never assume an action worked:

- After a navigation or a click that matters: `co browser take_screenshot` and look
  at the PNG, or read `get_text` / `get_current_url` output. Give the page a beat
  to settle between navigating and screenshotting.
- Before an irreversible action (submit, post, publish, pay): screenshot first,
  act **exactly once**, screenshot after. Never click the same submit button twice —
  if the result is ambiguous, report uncertain state instead of retrying.
- To find stable selectors, save the DOM and grep it:

  ```bash
  co browser save_page_context li_composer
  grep -o 'aria-label="[^"]*"' ~/.co/browser_context/*li_composer*/page.html | sort -u
  ```

- Site-specific DOM logic belongs in skill-local JS, not one-off shell parsing:

  ```bash
  co browser run_page_script .co/skills/<skill>/scripts/extract-items.js
  ```

## Step 5: React to exit codes

Branch on the exit code — don't parse prose:

| Code | Meaning | What to do |
|------|---------|------------|
| `0` | success | continue |
| `1` | action failed (e.g. selector not found) | inspect the error, adjust selector or approach |
| `2` | usage error (bad flags, empty `-t`, `tab` misuse) | fix the command syntax |
| `3` | unknown tab | `tab open` the name first, then target it |
| `4` | tab busy — another agent is mid-task there | do NOT retry the same command; open your own tab (the error shows the three commands) |

A crashed agent's tab claim expires on its own in ~2 minutes.

## Logging in

The default is a **visible** window — exactly what you want for a first login.
Never automate credentials: open the login page, let the human log in, poll until done:

```bash
co browser go_to https://site.com/login
# human logs in in the visible window; poll until the URL leaves the login page
for i in $(seq 1 30); do
  sleep 20
  co browser get_current_url | tail -1 | grep -q "/feed" && break
done
```

Logins live in the profile (`~/.co/browser_profile/`), not the daemon — they survive
`close` and daemon restarts. Log in once, stay logged in.

Headless: `co browser --headless go_to ...` — the choice is made by whichever command
**starts** the daemon and sticks for its lifetime. To switch: `close`, then relaunch.

## Scripting hygiene

- Wrap calls that might block in `timeout 60 co browser ...`; take the data line
  with `tail -1` when the output includes env banners.
- Read long pages in chunks: `co browser get_text | sed -n '1,200p'`.
- Batch related commands in one turn; never spend a whole turn on a bare wait.
- Don't screenshot while scanning — extracted text is the source of truth. Screenshot
  only at evidence gates (before/after an irreversible action).
- Uploads: try `upload_file_by_selector 'input[type="file"]' <path>` first; if the
  input is hidden behind a button, `upload_file_after_click_by_selector '<button selector>' <path>`.

## Troubleshooting

- **"Where is my window?"** — `co browser status` says `headless=true`? An earlier
  command started the daemon headless. `co browser close`, rerun without the flag.
- **exit 4 ("tab in use by ...")** — another agent is mid-task. Open your own tab.
- **"daemon is busy" after ~15s** — a long `do` holds the single-threaded daemon.
  Wait, then check `co browser status`.
- **"Opening in existing browser session" / profile in use (shows a PID)** — a
  manually opened Chrome or stale daemon holds the profile; kill that PID, retry.
- **`TargetClosedError` after a crash** — the page died under the daemon; run
  `co browser open_browser` again before retrying the command.
- **"Chrome failed to start"** — usually ssh/cron without a desktop session (run from
  a logged-in Terminal, or use `--headless`), or a leftover Chrome holding the
  profile. Full launch log: `~/.co/browser.log`.
- **Nuclear option** — kill the daemon and let the next command start fresh
  (logins survive — they live in the profile, not the daemon):

  ```bash
  pkill -f connectonion.cli.browser_agent.daemon
  ```

## Done checklist

- [ ] Identity set (`CO_WHO`) if scripted or concurrent
- [ ] Board checked (`status` / `tab ls`) before claiming a tab
- [ ] Own tab used if any other agent/task shares the browser (`-t` on every command)
- [ ] Irreversible actions performed exactly once, with before/after screenshots
- [ ] Tab closed (`co browser tab close <name>`) when the task is done
- [ ] Browser left open for the next task unless the user asked to `close`
