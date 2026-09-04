# The Model Was Holding the Browser

*2026-08-19*

Three browser sessions stopped making progress for roughly forty minutes. The
browser itself was mostly idle.

One session had asked `co browser do` to extract page data while its model
provider was over a spending cap. Each model call retried and waited. A single
attempt took more than four minutes; another took about a minute. Other agents
could not even ask the browser for status, and one eventually disconnected
before the daemon replied.

The queue was working exactly as written. That was the problem.

## One request contained the whole agent

The browser daemon deliberately executes one Playwright action at a time.
Patchright's synchronous driver belongs to one thread, and serializing short
clicks, navigations, and screenshots keeps two callers from corrupting the same
browser context.

But `do` was not a short browser action. The daemon received one request and ran
the entire agent loop inside it: think, call the model, drive the page, think
again, up to two hundred times. Model latency held the browser lane even though
no browser work was happening. The safety boundary around Playwright had grown
into a lock around the network.

## The agent became a client

The model loop now runs in the `co browser do` process. It receives a proxy with
the same tool signatures as `BrowserAutomation`, so the model sees the same
forty browser operations. Each proxy call is serialized into one ordinary
daemon request and releases the lane when that action finishes.

```text
model thinks locally
  → go_to request
  → daemon navigates and replies
model thinks locally
  → get_text request
  → daemon reads and replies
```

Tab ownership remains in the daemon and is checked on every action. Moving the
agent did not make two tasks safe on one page; named tabs are still the unit of
isolation. It only means an agent waiting on a provider no longer prevents work
on other tabs.

Screenshots needed one extra wire detail. Human shell commands should print the
saved image path, but the agent's vision formatter needs the original data URL.
Agent tool requests now ask for raw results, preserving vision without dumping
base64 into a person's terminal.

## Proving the absence of a lock

A regression test starts a fake model call and deliberately leaves it waiting.
While it waits, another client sends `status` through the real daemon transport
and receives an immediate answer. The test then releases the model and confirms
the `do` run completes. That is the behavior the incident lacked: model time is
caller time; only browser time belongs to the browser lane.
