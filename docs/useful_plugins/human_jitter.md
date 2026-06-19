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
2. If the tool name starts with `click`, grabs the `BrowserAutomation` instance off the tool registry (`agent.tools.browserautomation`).
3. Dispatches `jitter()` onto the browser's single worker thread (Playwright is not thread-safe): the cursor moves to a random point, then random-walks through 2–4 more, with short pauses.

Jitter is **best-effort** — if the page is mid-navigation when it reads the viewport, the failure is caught and logged, never raised, so the click the agent asked for still proceeds.

## Why `before_each_tool`

It's the only hook that fires synchronously between "LLM picked a click tool" and "Playwright performs the click" — exactly where pre-click motion belongs. `after_tools` is too late (the click already happened).

## Why a Plugin (not baked into `click`)

Jitter is non-deterministic and opt-in. Forcing it on every browser user would make clicks non-reproducible for tests and agents that don't want it. Opt in with `plugins=[human_jitter]`.

## Events

| Handler | Event | Purpose |
|---------|-------|---------|
| `_jitter_before_click` | `before_each_tool` | Wander the mouse before any `click*` tool runs |

## Notes

- Only affects tools whose name starts with `click` (`click`, `click_element_by_selector`, …); other tools are untouched.
- Cosmetic only — it raises a bot's trust score marginally, but egress IP reputation dominates anti-bot scoring. Pair with `BROWSER_PROXY` (see [Browser Tools](../useful_tools/browser_tools.md)) when that's the real bottleneck.

## Customizing

```bash
co copy human_jitter
```

```python
# from connectonion.useful_plugins import human_jitter  # Before
from plugins.human_jitter import human_jitter            # After
```
