# human_jitter

Make a browser agent's clicks look human: right before any `click*` tool runs, wander the mouse through a few random points on the page, so the click is preceded by organic motion instead of an instant teleport-and-click.

## Quick Start

```python
from connectonion import Agent
from connectonion.useful_tools.browser_tools import BrowserAutomation
from connectonion.useful_plugins import human_jitter

browser = BrowserAutomation()
agent = Agent("web", tools=[browser], plugins=[human_jitter])

agent.input("log into the site and click the verify checkbox")
# before each click*, the cursor drifts through a few points first
```

## How It Works

1. On `before_each_tool`, reads `agent.current_session['pending_tool']`.
2. If its name starts with `click`, grabs the `BrowserAutomation` instance off the tool registry (`agent.tools.browserautomation`).
3. Dispatches `jitter()` onto the browser's single worker thread: the cursor moves to a random point, then random-walks through a few more, with short pauses.

Jitter is best-effort. If the page is mid-navigation when it reads the viewport, the failure is caught and logged so the click the agent asked for can still proceed.

## Why a Plugin

Jitter is non-deterministic and opt-in. Forcing it on every browser user would make clicks non-reproducible for tests and agents that do not want it. Opt in with `plugins=[human_jitter]`.

## Notes

- Only affects tools whose name starts with `click` (`click`, `click_element_by_selector`, and similar browser tools).
- Pair with `BROWSER_PROXY` when egress IP reputation is the real bottleneck.
