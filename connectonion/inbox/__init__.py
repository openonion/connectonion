"""
Purpose: Inbound chat channels as inbox directories — `co feishu listen`, `co feishu receive`, `co feishu send`
LLM-Note:
  Dependencies: imports from [inbox/store.py] | imported by [cli/commands/listen_commands.py] | provider modules (inbox/feishu.py) are imported lazily by name so a missing SDK costs nothing until that provider is used
  Data flow: provider(name) → a provider object with check(), run(inbox), send() | Inbox(name) → the directory
  State/Effects: none of its own
  Integration: exposes Message, Inbox, provider(), PROVIDERS | nothing here imports core/ or network/host/: the tool knows nothing about Agents, Hosts, OIP or trust, on purpose (DD-063)
  Errors: provider() raises ValueError for a name it does not know
"""

import os

from .store import Inbox, Message

# The queue, drawn where the people in the chat can see it. A message the bot
# would answer is marked as it is queued and re-marked the moment a reply is
# actually being sent, and the platforms replace a sender's previous reaction
# rather than stacking them, so the pair reads as one changing status.
#
# Two, not one: the interval between them is where a consumer is running or a
# model is thinking, and one marker that never changes cannot say whether
# anything is happening — which from the group's side is indistinguishable from
# the bot being down. It doubles as the cheapest debugger there is. Nothing
# means the message never arrived; SEEN alone means nothing picked it up;
# ANSWERING with no answer means the reply path failed.
SEEN = "👀"
ANSWERING = "✍️"


class ListenerStopped(RuntimeError):
    """The connection ended in a way no amount of waiting will recover from.

    Separate from every other listener failure because the answer is different:
    being unlinked, having the session taken by another client, or being banned
    all need a person, and no restart helps. Every other disconnection is
    transient and the provider reconnects from it.

    Lives here rather than in a provider because the distinction is not
    WhatsApp's — any platform can end a session for good — and because the
    command layer has to catch it without importing a provider it may not have
    the SDK for.
    """


class ProviderPolicyError(RuntimeError):
    """The platform's rules forbid this send, and retrying will not change it.

    Different from a failed send because the fix is a person's, not time's:
    WhatsApp's Cloud API refuses free text once the customer has been silent
    for 24 hours, and only a pre-approved template or a new message from them
    reopens it. The command layer exits 3 on it, the "a person has to act"
    code, so a supervisor that retries on 1 does not retry this.
    """


def reactions_enabled() -> bool:
    """Whether to mark messages at all.

    On by default, because the feedback is the point and the bot only ever
    marks messages addressed to it. `CO_INBOX_REACT=0` turns it off, because it
    is a visible action in somebody else's group and that deserves a switch.
    """
    return os.environ.get("CO_INBOX_REACT", "1").strip().lower() not in {"0", "false", "no", "off"}


# name → (module, class, constructor kwargs). Lark is Feishu with a different
# domain and its own credentials, not a second implementation. WhatsApp needs
# an extra (`pip install 'connectonion[whatsapp]'`), which costs nothing here:
# the module is imported by name only when someone asks for that provider.
PROVIDERS = {
    "feishu": ("connectonion.inbox.feishu", "Feishu", {"domain": "feishu"}),
    "lark": ("connectonion.inbox.feishu", "Feishu", {"domain": "lark"}),
    "whatsapp": ("connectonion.inbox.whatsapp", "WhatsApp", {}),
    # Not a second WhatsApp implementation: a different account type. `whatsapp`
    # is a linked device on a phone number; `whatsapp-cloud` is Meta's Business
    # Cloud API, with its own credentials and its own inbox directory.
    "whatsapp-cloud": ("connectonion.inbox.whatsapp_cloud", "WhatsAppCloud", {}),
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


__all__ = ["Inbox", "Message", "provider", "PROVIDERS",
           "SEEN", "ANSWERING", "reactions_enabled", "ListenerStopped",
           "ProviderPolicyError"]
