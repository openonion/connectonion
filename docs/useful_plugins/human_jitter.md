# human_jitter

Move the cursor along an organic path before a click instead of teleporting straight to the target. Some interfaces only reveal or enable a control after real pointer movement (hover menus, lazy-loaded widgets, drag affordances), so a single teleport-click can land on nothing — a short wander first makes the interaction land. Use it on sites whose terms permit automation.

## Quick Start

```python
from connectonion import Agent
from connectonion.useful_tools.browser_tools import BrowserAutomation
from connectonion.useful_plugins import human_jitter

browser = BrowserAutomation()
agent = Agent("web", tools=[browser], plugins=[human_jitter])

agent.input("open the menu and click Settings")
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
- Respect each site's terms of service and `robots`/automation policy when enabling it.
