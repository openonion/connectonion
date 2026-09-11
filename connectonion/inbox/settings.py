"""
Purpose: Which channels an agent listens to, written in .co/host.yaml so that starting needs no flags
LLM-Note:
  Dependencies: imports from [dataclasses, pathlib, yaml, inbox/__init__.py for PROVIDERS] | imported by [cli/co_ai/listen.py, network/host/inbox.py] | tested by [tests/unit/test_inbox_settings.py]
  Data flow: .co/host.yaml `listen:` → channels_from(mapping) → [Channel] | Channel.answers(message) → the one gate 1.8.5 applies
  State/Effects: reads one file; writes nothing
  Integration: host.yaml already holds `name` and `trust`, so a channel belongs beside them; --listen replaces the list for one run, --no-listen empties it
  Errors: an unknown channel name and a host.yaml that does not parse both raise ValueError rather than starting with no channels, because an agent nobody can reach looks exactly like a working one

Reading host.yaml here is a file read, not a dependency: this module imports
nothing from core/ or network/host/, so the DD-063 rule about what the inbox
package may know still holds.

The gate is deliberately one line long. In 1.8.5 anyone who can address the bot
can command the Agent — a self-built application is scoped to one tenant and to
the groups the bot was invited to, so "anyone" is the company, not the internet.
Sender allowlists and the trust levels are 1.9 (#1479); the requester is
recorded from the first release so that they need no migration.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, List, Optional, Sequence


@dataclass(frozen=True)
class Channel:
    """One inbound channel and the little that is decided about it."""

    provider: str
    chats: tuple = ()
    mention_only: bool = True

    def answers(self, message) -> bool:
        """Whether this message is for us.

        `mentioned` is the provider's own answer to "was the bot addressed",
        and it is true for a direct message, so one test covers both shapes.
        """
        if self.chats and message.chat not in self.chats:
            return False
        return bool(message.mentioned) or not self.mention_only


def _known() -> List[str]:
    from . import PROVIDERS

    return sorted(PROVIDERS)


def _channel(name: str, options) -> Channel:
    if name not in _known():
        raise ValueError(
            f"unknown channel {name!r} in host.yaml listen:; known: {', '.join(_known())}")
    options = options or {}
    if not isinstance(options, dict):
        raise ValueError(f"listen: {name}: expected a mapping of options, got {type(options).__name__}")
    chats = options.get("chats") or ()
    if isinstance(chats, str):
        chats = (chats,)
    return Channel(
        provider=name,
        chats=tuple(str(chat) for chat in chats),
        mention_only=bool(options.get("mention_only", True)),
    )


def channels_from(listen) -> List[Channel]:
    """Parse a `listen:` value. A mapping carries options; a list is names."""
    if not listen:
        return []
    if isinstance(listen, str):
        listen = [listen]
    if isinstance(listen, dict):
        return [_channel(name, options) for name, options in listen.items()]
    if isinstance(listen, (list, tuple)):
        return [_channel(entry, {}) if isinstance(entry, str)
                else _channel(*next(iter(entry.items()))) for entry in listen]
    raise ValueError(f"listen: expected a mapping or a list, got {type(listen).__name__}")


def configured_channels(co_dir: Path = Path(".co"),
                        override: Optional[Sequence[str]] = None) -> List[Channel]:
    """The channels to listen to: the file, unless the command line says otherwise.

    `override=None` means no flag was given and the file decides, which is the
    normal case. A list replaces which channels run — not how they are
    configured, so a channel named on the command line still takes its options
    from the file.
    """
    host_yaml = Path(co_dir) / "host.yaml"
    configured: List[Channel] = []
    if host_yaml.exists():
        import yaml

        try:
            config = yaml.safe_load(host_yaml.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError as error:
            raise ValueError(f"{host_yaml} does not parse: {error}") from error
        if isinstance(config, dict):
            configured = channels_from(config.get("listen"))

    if override is None:
        return configured
    settings = {channel.provider: channel for channel in configured}
    return [settings.get(name) or _channel(name, {}) for name in override]
