# ConnectOnion Features

Simple features for agent developers.

## Core Features

1. **[@agent decorator](01-agent-decorator.md)** - Make functions discoverable
2. **[discover()](02-discover.md)** - Find agents by what they do
3. **[Test before trust](03-test-before-trust.md)** - Try agents safely
4. **[serve](04-serve.md)** - Share your agents

## Composition

5. **[Compose agents](05-compose-agents.md)** - Chain agents together
6. **[Pipeline](14-pipeline.md)** - Build reusable workflows

## Trust & Reliability

7. **[my_experience](06-my-experience.md)** - Track your agent history
8. **[Fallback](07-fallback.md)** - Handle failures gracefully
9. **[Monitor](10-monitor.md)** - Track agent health

## Analytics

10. **[Agent stats](08-agent-stats.md)** - See how your agents are used
11. **[Cost tracking](11-cost-tracking.md)** - Monitor spending

## Developer Tools

12. **[REPL](09-repl.md)** - Interactive development
13. **[Visual network](12-visual-network.md)** - See agents in action
14. **[Replay](13-replay.md)** - Time-travel debugging

## Performance

15. **[Local first](15-local-first.md)** - Works offline

## Design Principles

- One line to make discoverable
- One line to discover others
- Everything else automatic
- No configuration needed
- Trust through experience

## Getting Started

```python
# 1. Make your function discoverable
from connectonion import agent

@agent
def translate(text: str, to_lang: str) -> str:
    return my_translation(text, to_lang)

# 2. Discover other agents
from connectonion import discover

summarizer = discover("summarize text")
summary = summarizer(long_text)

# That's it!
```