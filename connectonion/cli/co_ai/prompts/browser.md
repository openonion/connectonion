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

**Multiple pages.** Every command targets the main tab unless you pass `-t`:

```
bash("co browser -t research go_to https://example.com")
```

Use a named tab when you need a second page open at the same time; do not open
a second tab for work that fits in one.

**Exit codes.** A non-zero exit means the command failed — read the message
rather than assuming the action happened. `co browser` reporting the daemon is
busy means another caller holds it; wait and retry rather than killing it.
