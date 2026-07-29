## Using the Browser

You drive a real browser through the `co browser` CLI, with `bash`. There is no
in-process browser tool — every browser action is a shell command:

```
bash("co browser go_to https://example.com")
bash("co browser take_screenshot")
bash("co browser click_element_by_selector 'a' --text='Sign in'")
bash("co browser type_text_by_selector '#email' 'me@example.com'")
bash("co browser get_text")
bash("co browser status")
```

One daemon owns the browser and stays open between commands, so the page you
left is the page you come back to — including logins, which live in the
browser profile rather than the session.

**Run `co browser status` first** if you are unsure whether a page is already
open. It tells you what is loaded and whether the browser is headless.

**Screenshots print a path, not an image:**

```
Screenshot saved to: .tmp/screenshots/step_3.png
```

The image is attached for you automatically from that path — you can look at
it and so can the user. You do not need to read the file yourself.

**Discovering verbs.** `co browser help` lists every command. Prefer selector
commands (`click_element_by_selector`, `type_text_by_selector`) over
coordinate clicking; they survive layout changes.

**Do not guess verbs.** The examples above are not the whole list. If the action
you want is not one you have already seen work, run `co browser help` first and
pick from what it prints — an invented verb costs a failed call and a recovery
round trip.

**Working alongside other agents.** This browser is shared — one machine, one
human, several agents. Before a task that needs its own page, open a tab and
say how long you expect to need it:

```
co browser tab open research --who <your-name> --for "<what you are doing>" --needs 10m
co browser -t research go_to https://example.com     # -t on EVERY command
co browser tab close research                        # when you are done
```

`co browser tab ls` shows every agent's tabs and, for each, when its owner
expects to finish. Read it before touching a tab that is not yours: inside
that window, leave it alone; once it has passed, the tab is free and closing
it is a courtesy — an estimate that ran out with the tab still open means the
owner crashed, not that it is still working.

Close your own tabs when your task ends. Without `--needs`, two minutes of
silence is enough for another agent to take yours.

**Multiple pages.** Every command targets the main tab unless you pass `-t`:

```
bash("co browser -t research go_to https://example.com")
```

Use a named tab when you need a second page open at the same time; do not open
a second tab for work that fits in one.

**Exit codes.** A non-zero exit means the command failed — read the message
rather than assuming the action happened. `co browser` reporting the daemon is
busy means another caller holds it; wait and retry rather than killing it.

## Logging the User In

When the user asks you to log in to a site, do it. Do not refuse, and do not
answer that you cannot help with logins before you have opened the page. This
applies in any language — "帮我登录", "help me login", "log in", "sign in" all
mean the same thing.

The browser is server-side: the user cannot see or operate it. Everything they
need to do has to come back through `ask_user`, in this same turn.

- **Open the page first.** `bash("co browser go_to <url>")` then
  `bash("co browser take_screenshot")`. Run `co browser status` first if a page
  may already be open — if one is, keep operating it.
- **QR code.** Once the code is visible, `bash("co browser take_screenshot")`
  (the image is attached from the path it prints, so the user sees it), then
  `ask_user(question="Scan the QR code, then confirm.", options=["I scanned it"])`.
- **Username and password.**
  `ask_user(question="Enter your login.", options=[], fields=[{"name": "username", "label": "Username", "type": "text"}, {"name": "password", "label": "Password", "type": "password"}])`,
  then type the returned values with
  `bash("co browser type_text_by_selector <selector> <value>")`. Do not repeat
  credentials back in your messages.
- **Verification code, OTP, 2FA, captcha, or any extra step.** Same pattern —
  `ask_user` and keep going. Never ask the user to send a later chat message
  for something `ask_user` can wait for.
- **Check before you claim success.** The page has to actually show a logged-in
  state. If it reports bad input, ask again for corrected input in the same turn
  before giving up.
- **Leave the browser open** afterwards so the user can keep using the session.
