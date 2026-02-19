import json
import random
from pathlib import Path
from rich.console import Console

console = Console()

TIPS = [
    {
        "text": "Use @xray decorator on any tool to pause and inspect agent state during execution.",
        "link": "docs.connectonion.com/xray",
        "context": ["create", "init"],
    },
    {
        "text": 'Try model="co/gemini-2.5-pro" for free managed LLM access — no API key needed.',
        "link": "docs.connectonion.com/models",
        "context": ["auth", "status"],
    },
    {
        "text": "Add type hints to tool functions for better LLM schema generation.\n    def search(query: str, limit: int = 10) -> list: ...",
        "link": "docs.connectonion.com/tools",
        "context": ["create", "init"],
    },
    {
        "text": "Use host() and connect() to build multi-agent systems that collaborate.\n    from connectonion.network import host, connect",
        "link": "docs.connectonion.com/network",
        "context": ["create", "init", "deploy"],
    },
    {
        "text": "The event system lets you hook into agent lifecycle: after_llm, after_tools, on_complete.\n    agent = Agent('name', on_events=[after_tools(my_handler)])",
        "link": "docs.connectonion.com/events",
        "context": ["create", "init"],
    },
    {
        "text": "Plugins bundle event handlers together — try the built-in reflection plugin.\n    from connectonion.useful_plugins import reflection",
        "link": "docs.connectonion.com/plugins",
        "context": ["create", "init"],
    },
    {
        "text": "co browser launches a browser automation agent. Try: co -b 'find flights to Tokyo'",
        "link": "docs.connectonion.com/browser",
        "context": ["create", "status", "auth"],
    },
    {
        "text": "Use co/ prefix models for managed keys: model='co/gemini-2.5-flash' for fast, cheap tasks.",
        "link": "docs.connectonion.com/models",
        "context": ["status", "auth", "keys"],
    },
    {
        "text": "Join our Discord for help, tips, and to share your agents.\n    discord.gg/4xfD9k8AUF",
        "link": "discord.gg/4xfD9k8AUF",
        "context": [],
    },
    {
        "text": "Add connect.py integrations for Gmail/Calendar with: co auth google",
        "link": "docs.connectonion.com/email",
        "context": ["auth", "create", "init"],
    },
    {
        "text": "Use quiet=True to suppress console output for background agents.\n    agent = Agent('name', quiet=True)",
        "link": "docs.connectonion.com/logging",
        "context": ["create", "init"],
    },
    {
        "text": "llm_do() runs a one-shot LLM call without creating a full agent.\n    from connectonion import llm_do",
        "link": "docs.connectonion.com/llm-do",
        "context": ["create", "init"],
    },
    {
        "text": "Use agent.receive_all() to iterate over streaming events from a remote agent.",
        "link": "docs.connectonion.com/network",
        "context": ["create", "deploy"],
    },
    {
        "text": "co copy <tool> copies built-in tool source to your project for customization.\n    co copy send_email",
        "link": "docs.connectonion.com/tools",
        "context": ["create", "init", "copy"],
    },
    {
        "text": "Set max_iterations on your agent to control how long it runs.\n    agent = Agent('name', max_iterations=50)",
        "link": "docs.connectonion.com/agent",
        "context": ["create", "init"],
    },
    {
        "text": "Use structured_complete() to get typed Pydantic output from LLMs.\n    llm.structured_complete(messages, MySchema)",
        "link": "docs.connectonion.com/llm",
        "context": ["create", "init"],
    },
    {
        "text": "Sessions are saved to .co/evals/ as YAML for debugging and replaying.",
        "link": "docs.connectonion.com/sessions",
        "context": ["eval", "status"],
    },
    {
        "text": "co eval runs your eval files and shows pass/fail results.",
        "link": "docs.connectonion.com/eval",
        "context": ["eval"],
    },
    {
        "text": "Use trust='careful' in host() to require signature verification from remote agents.",
        "link": "docs.connectonion.com/trust",
        "context": ["deploy", "create"],
    },
    {
        "text": "Full docs at docs.connectonion.com — includes tutorials, API reference, and examples.",
        "link": "docs.connectonion.com",
        "context": [],
    },
]

_TIPS_SEEN_FILE = Path.home() / ".co" / "tips_seen.json"
_CONFIG_FILE = Path.home() / ".co" / "config.toml"


def _tips_enabled() -> bool:
    if not _CONFIG_FILE.exists():
        return True
    import toml
    config = toml.load(_CONFIG_FILE)
    return config.get("cli", {}).get("tips", True)


def _load_seen() -> list:
    if not _TIPS_SEEN_FILE.exists():
        return []
    return json.loads(_TIPS_SEEN_FILE.read_text())


def _save_seen(seen: list):
    _TIPS_SEEN_FILE.parent.mkdir(parents=True, exist_ok=True)
    _TIPS_SEEN_FILE.write_text(json.dumps(seen))


def show_tip(command: str):
    if not _tips_enabled():
        return

    seen = _load_seen()

    # Find tips matching this command context, preferring unseen ones
    contextual = [t for t in TIPS if command in t["context"]]
    universal = [t for t in TIPS if not t["context"]]
    candidates = contextual + universal

    # Filter unseen; if all seen, reset rotation
    unseen = [t for t in candidates if t["text"] not in seen]
    if not unseen:
        # All seen - reset and show any
        seen = []
        unseen = candidates

    if not unseen:
        return

    tip = random.choice(unseen)
    seen.append(tip["text"])

    # Keep seen list bounded
    if len(seen) > len(TIPS):
        seen = seen[-len(TIPS):]

    _save_seen(seen)

    console.print()
    console.print(f"[bold yellow]💡 Tip:[/bold yellow] {tip['text']}")
    console.print(f"   [dim]Learn more: {tip['link']}[/dim]")
