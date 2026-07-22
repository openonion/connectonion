# Hosted browser agent

A production-shaped browser automation agent: one shared stealth browser
(Patchright + persistent login profile), served to many concurrent chat
sessions, with site workflows packaged as skills. This is the same shape that
runs real social-media agents (login once, then post / scrape / engage on a
schedule or on demand).

## Run it

```bash
python agent.py "open https://example.com and describe the page"   # one-shot local run
python agent.py                                                     # serve (HTTP/WS + relay)
```

Local runs open a visible browser window — log in to your sites by hand once
(or let the agent call `wait_for_manual_login`); cookies persist in
`~/.co/browser_profile` and every later run starts signed in.

## Teach it a site: skills

Site workflows live in `.co/skills/<name>/SKILL.md` — the agent discovers them
automatically and its own prompt stays site-agnostic. One skill per workflow:

```
.co/skills/
  mysite-login/SKILL.md      # how to sign in; credentials via ask_user
  mysite-post/SKILL.md       # draft + submit, two-phase
  mysite-scrape/SKILL.md     # extract items with selectors
```

`SKILL.md` = YAML frontmatter (`name`, `description`) + step-by-step
instructions. Write steps against the browser tools (`go_to`, `click`,
`type_text_by_selector`, `extract_items_by_selector`, `take_screenshot`, ...)
and state checks ("if you see the login form, run /mysite-login first").
Complex page manipulation can ship as a JS file next to the skill and run via
`run_frame_script`.

Develop a skill with one-shot runs (`python agent.py "/mysite-login"`), then
deploy the same directory.

## Deploy

```bash
co deploy
```

The Dockerfile runs the headed browser under Xvfb (real sites treat headless
fingerprints as bots). For a server that must start already signed in, export
your local login with the browser's `save_state` tool and pass the file via
`BrowserAutomation(seed_state=...)` from your deploy secret store — never
commit it.

## Drive it directly (no LLM): `remote.call`

Sometimes you don't want the agent to *think* — you just want to run a browser
step and see the result, like a remote command line:

```python
from connectonion import connect

remote = connect("0x...", keys=my_keys)

# Run one tool, get the raw result straight back — no reasoning, no history.
remote.call("go_to", url="https://example.com")
shot = remote.call("take_screenshot")
if shot.images:               # base64 data URLs extracted from the output
    open("page.png", "wb").write(base64.b64decode(shot.images[0].split(",")[1]))
```

`remote.call(tool, **args)` returns an `ExecResult(text, status, duration_ms,
error)`: `.ok` is True on success and `.images` pulls any base64 screenshots out
of the output. It runs over the same authenticated WebSocket as `input()`, so
relay discovery and trust still apply.

What may run this way is the `.co/host.yaml` **permissions** whitelist — the very
same list that lets the LLM auto-run a command without asking. The browser
navigation/observation tools (`go_to`, `take_screenshot`, `click`, `scroll`, ...)
and `co ...` CLI commands are whitelisted by default; add a line to `host.yaml`
to expose more, e.g. `"Bash(git status)"`. Anything not on the list stays behind
the agent's judgement via `input()`.

## Knobs that matter in production

- `BrowserAutomation(tab_idle_ttl=600, max_tabs=3)` — each chat session gets
  its own tab in the shared browser; these bound tab memory on small boxes.
- The idle reaper in `agent.py` closes the whole browser after 2h without tool
  calls (frees Chromium's ~1GB); it relaunches lazily, login intact.
- `BROWSER_PROXY=socks5://host:port` (or `http://user:pass@host:port`) in
  `.env` routes browser egress through a proxy — residential egress avoids the
  datacenter-IP checkpoints many sites serve.
- Credentials and 2FA always flow through `ask_user` at runtime; the agent
  never stores them.
