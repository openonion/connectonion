"""
Purpose: Inbound chat channels as inbox directories — `co feishu listen`, `co feishu receive`, `co feishu send`
LLM-Note:
  Dependencies: imports from [inbox/store.py] | imported by [cli/commands/listen_commands.py] | provider modules (inbox/feishu.py) are imported lazily by name so a missing SDK costs nothing until that provider is used
  Data flow: provider(name) → a provider object with check(), run(inbox), send() | Inbox(name) → the directory
  State/Effects: none of its own
  Integration: exposes Message, Inbox, provider(), PROVIDERS | nothing here imports core/ or network/host/: the tool knows nothing about Agents, Hosts, OIP or trust, on purpose (DD-063)
  Errors: provider() raises ValueError for a name it does not know
"""

from .store import Inbox, Message

# name → (module, class, constructor kwargs). Lark is Feishu with a different
# domain and its own credentials, not a second implementation.
PROVIDERS = {
    "feishu": ("connectonion.inbox.feishu", "Feishu", {"domain": "feishu"}),
    "lark": ("connectonion.inbox.feishu", "Feishu", {"domain": "lark"}),
}


def provider(name: str):
    """The provider object for a channel name."""
    try:
        module_name, class_name, kwargs = PROVIDERS[name]
    except KeyError:
        raise ValueError(f"unknown provider {name!r}; known: {', '.join(sorted(PROVIDERS))}")
    import importlib

    module = importlib.import_module(module_name)
    return getattr(module, class_name)(**kwargs)


__all__ = ["Inbox", "Message", "provider", "PROVIDERS"]
