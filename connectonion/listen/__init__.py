"""
Purpose: Inbound chat channels as mailbox directories — `co feishu listen`, `co feishu receive`, `co feishu send`
LLM-Note:
  Dependencies: imports from [listen/mailbox.py] | imported by [cli/commands/listen_commands.py] | provider modules (listen/feishu.py) are imported lazily by name so a missing SDK costs nothing until that provider is used
  Data flow: provider(name) → a provider object with check(), run(mailbox), send() | Mailbox(name) → the directory
  State/Effects: none of its own
  Integration: exposes Message, Mailbox, provider(), PROVIDERS | nothing here imports core/ or network/host/: the tool knows nothing about Agents, Hosts, OIP or trust, on purpose (DD-063)
  Errors: provider() raises ValueError for a name it does not know
"""

from .mailbox import Mailbox, Message


class ProviderPolicyError(RuntimeError):
    """A provider policy makes this send invalid without new user action."""

# name → (module, class, constructor kwargs). Lark is Feishu with a different
# domain and its own credentials, not a second implementation.
PROVIDERS = {
    "feishu": ("connectonion.listen.feishu", "Feishu", {"domain": "feishu"}),
    "lark": ("connectonion.listen.feishu", "Feishu", {"domain": "lark"}),
    "telegram": ("connectonion.listen.telegram", "Telegram", {}),
    "discord": ("connectonion.listen.discord", "Discord", {}),
    "whatsapp": ("connectonion.listen.whatsapp", "WhatsApp", {}),
}


def provider(name: str):
    """The provider object for a mailbox name."""
    try:
        module_name, class_name, kwargs = PROVIDERS[name]
    except KeyError:
        raise ValueError(f"unknown provider {name!r}; known: {', '.join(sorted(PROVIDERS))}")
    import importlib

    module = importlib.import_module(module_name)
    return getattr(module, class_name)(**kwargs)


__all__ = ["Mailbox", "Message", "ProviderPolicyError", "provider", "PROVIDERS"]
