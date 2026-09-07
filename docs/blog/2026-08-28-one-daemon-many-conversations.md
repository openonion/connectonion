# One Daemon, Many Conversations

The browser daemon had a fairness problem with a long history: it served
exactly one request at a time, in arrival order, holding the line until the
current one finished. For quick verbs — navigate, screenshot, click — nobody
noticed. The day an agent-driven `do` run took forty minutes, three other
sessions discovered they were standing in a queue behind it, and the browser
those sessions needed sat idle for most of that time, because most of a
model-driven step is spent waiting on the model, which needs no browser.

1.8.0a2 ends the serial era, and the interesting part is what it refused to
change to get there. The public API stays synchronous — every existing
script, skill, and muscle memory calls the same `BrowserAutomation` methods
with the same signatures. Underneath, the driver core is async and the
daemon runs sessions concurrently; the synchronous surface is a facade over
the async engine, not a parallel implementation that would drift from it.

The ordering rule that matters is per-session, not global: your own steps
still happen in the order you issued them, because a session's frames form
one logical conversation. What disappeared is the false coupling *between*
conversations — session B's screenshot no longer waits for session A's
forty-minute errand.

The lesson generalizes past browsers: when one worker serves many
conversations, the coupling you must break is *between* conversations, and
the compatibility you must not break is *within* one. Getting those the
right way round is the whole difference between a rewrite users celebrate
and one they have to migrate through.
