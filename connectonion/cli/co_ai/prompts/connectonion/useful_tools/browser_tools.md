# browser_tools

Drive a real browser: navigate, click, type, upload, screenshot.

In current versions the agent drives the browser through the **`co browser`
CLI** against one shared, already-logged-in browser, rather than through
in-process tools. That is what makes a login survive between runs and lets
several agents share one session.

```bash
co browser tab open work --who agent --for "fill the form"
co browser -t work go_to https://example.com
co browser -t work click_element_by_selector 'button[type=submit]'
co browser -t work take_screenshot /tmp/after.png
co browser tab close work
```

## The rules that matter

**One task, one tab.** Open your own tab and pass `-t <tab>` to every command.
The browser is shared; a bare command on `main` collides with whatever else is
running.

**Verify with your eyes.** After any state-changing step, take a screenshot and
read it before the next one. A click that reported success is not proof the page
did what you expected.

**Never `pkill` the browser to fix a busy daemon** — it destroys other agents'
sessions. Open your own tab and wait instead.

See the `co-browser` skill for the full command reference.
