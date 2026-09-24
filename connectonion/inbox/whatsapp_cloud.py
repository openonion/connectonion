"""
Purpose: WhatsApp Cloud API as an inbox — Meta's webhook lands in O API, a lease-based poll writes files, replies go straight to Meta
LLM-Note:
  Dependencies: imports from [os, re, time, requests, backend.py, credentials.py, inbox/__init__.py, inbox/store.py, inbox/formatting.py] | imported by [inbox/__init__.py via provider()] | tested by [tests/unit/test_inbox_whatsapp_cloud.py]
  Data flow: Meta webhook → O API's webhook for this binding (signature checked and stored there, never called from here) → run(inbox) claims under a lease → to_message() → inbox.deliver() → ACK | a failed local write → NACK, and an expired lease makes the event claimable again | send()/reply → POST graph.facebook.com/{version}/{phone_number_id}/messages with the operator's own token
  State/Effects: reads WHATSAPP_CLOUD_* and OPENONION_API_KEY from the environment | no socket held open and no port opened: the listener is an HTTPS poll | writes connection.json on every state change so `check` can say whether the poll is working
  Integration: `co whatsapp-cloud`, separate from `co whatsapp` (the linked-device provider) — different account type, different credentials, its own inbox directory ~/.co/inbox/whatsapp-cloud/ | bind() is the one extra verb: it registers the webhook routing with O API
  Errors: check() returns each missing item with its next action | a 24-hour-window refusal (Meta 131047) raises ProviderPolicyError, which the CLI exits 3 on | O API refusing the account, or not serving the route at all, stops the listener with ListenerStopped instead of retrying forever | every error string is redacted of the four secrets before it is raised

Why the webhook is not the inbox.  Meta delivers a webhook once, and a 200 is
all it waits for.  If the receiver returned 200 and then failed to write the
message down, Meta would not retry and the message would exist nowhere.  So
O API only stores the signed event, and delivery finishes here, on the
operator's disk: claim, write, then ACK.  A write that fails is NACKed; a
process that dies holding a claim lets the lease lapse.  The ACK sits after
the write on purpose, even though one line earlier reads more cleanly.

Why the access token never leaves this machine.  Routing replies through O API
too would have been tidier, and it would have put the operator's Cloud API
token in a service that has no need for it.  O API holds the webhook app
secret (encrypted) and a hash of the verify token, which is exactly what it
needs to check Meta's signature; replies go from here to Meta directly.
"""

import os
import re
import time
from typing import Optional

import requests

from . import ListenerStopped, ProviderPolicyError
from .formatting import to_whatsapp
from .store import Inbox, Message, iso_utc

GRAPH = "https://graph.facebook.com"
ENV = "WHATSAPP_CLOUD_"
_VERSION = re.compile(r"^v[0-9]+\.[0-9]+$")

# Meta's "re-engagement message" error: the customer has not written in the
# last 24 hours, so only a pre-approved template may be sent. No retry and no
# reconnect changes that; a person has to write first, or someone has to get
# a template approved.
SERVICE_WINDOW_ERROR = 131047

# The O API side of this is openonion/oo-api#227. A 404 on the claim route is
# that route not being deployed, not an empty inbox, and saying so is the
# difference between a listener that looks idle and one that says why.
INBOX_ROUTE = "/api/v1/messaging/inbox/whatsapp/claim"


class Refused(RuntimeError):
    """O API answered and said no. Carries the status so the listener can
    tell "try again" (5xx) from "a person has to act" (401, 403, 404)."""

    def __init__(self, message: str, status: int):
        super().__init__(message)
        self.status = status


class WhatsAppCloud:
    """One WhatsApp Business phone number on Meta's Cloud API."""

    name = "whatsapp-cloud"

    # Verbs every inbox provider has and this one cannot do, with the reason in
    # the reader's terms. The Cloud API has no edit or delete for a business
    # message; a bare "not implemented" would read as a bug to be fixed here.
    cannot = {
        "edit": "the WhatsApp Cloud API cannot edit a message once it is sent",
        "delete": "the WhatsApp Cloud API cannot delete a sent message",
    }

    def __init__(self):
        self.access_token = _env("ACCESS_TOKEN")
        self.phone_number_id = _env("PHONE_NUMBER_ID")
        self.binding_id = _env("BINDING_ID")
        self.graph_version = _env("GRAPH_VERSION")

    # ---- setup -------------------------------------------------------------

    def missing(self) -> list:
        """Configuration problems, each with the fix. Empty means complete."""
        problems = []
        if not os.environ.get("OPENONION_API_KEY"):
            problems.append("OPENONION_API_KEY is not set. Next: co auth")
        if not self.access_token:
            problems.append(
                f"{ENV}ACCESS_TOKEN is not set: the Cloud API token from your Meta app. "
                f"Next: co env set {ENV}ACCESS_TOKEN <token>")
        if not self.phone_number_id:
            problems.append(
                f"{ENV}PHONE_NUMBER_ID is not set: the id Meta shows beside the number, "
                f"not the number. Next: co env set {ENV}PHONE_NUMBER_ID <id>")
        if not _VERSION.fullmatch(self.graph_version):
            problems.append(
                f"{ENV}GRAPH_VERSION must name a Meta Graph API version such as v23.0, "
                f"so a Meta upgrade cannot change delivery underneath you. "
                f"Next: co env set {ENV}GRAPH_VERSION v23.0")
        if not self.binding_id:
            problems.append(
                f"{ENV}BINDING_ID is not set: nothing routes Meta's webhook to this "
                f"account yet. Next: co whatsapp-cloud bind")
        return problems

    def bind_missing(self) -> list:
        """What `bind` needs. Read from the environment only: an app secret on
        argv is an app secret in shell history and in `ps`."""
        required = ("WABA_ID", "PHONE_NUMBER_ID", "APP_SECRET", "VERIFY_TOKEN")
        problems = [f"{ENV}{key} is not set. Next: co env set {ENV}{key} <value>"
                    for key in required if not _env(key)]
        if not os.environ.get("OPENONION_API_KEY"):
            problems.append("OPENONION_API_KEY is not set. Next: co auth")
        return problems

    def bind(self) -> dict:
        """Register this number's webhook routing with O API. Returns the
        binding, whose `id` goes in WHATSAPP_CLOUD_BINDING_ID."""
        return self._o_api("put", "/api/v1/messaging/bindings/whatsapp", json={
            "waba_id": _env("WABA_ID"),
            "phone_number_id": self.phone_number_id,
            "app_secret": _env("APP_SECRET"),
            "verify_token": _env("VERIFY_TOKEN"),
        })

    def check(self) -> list:
        """Everything that must be true before `listen` can work."""
        problems = self.missing()
        if problems:
            return problems
        try:
            bindings = self._o_api("get", "/api/v1/messaging/bindings").get("bindings") or []
            if not any(str(row.get("id")) == self.binding_id for row in bindings):
                problems.append(
                    f"{ENV}BINDING_ID {self.binding_id} is not a binding of this OpenOnion "
                    f"account. Next: co whatsapp-cloud bind")
        except Exception as exc:
            problems.append(f"O API could not list bindings: {exc}")
        try:
            self._meta("get", f"/{self.phone_number_id}", params={"fields": "id"})
        except Exception as exc:
            problems.append(f"Meta refused this token for {ENV}PHONE_NUMBER_ID: {exc}")
        return problems

    # ---- inbound -----------------------------------------------------------

    def run(self, inbox: Inbox, *, raw: bool = False, sleep=time.sleep) -> None:
        """Claim, write, ACK, forever. Blocks.

        A transient failure backs off to 30 seconds and retries. O API saying
        the account or the route is not there stops, because it will still
        not be there in 30 seconds.
        """
        delay = 1.0
        state = None
        while True:
            try:
                delivered = self._poll_once(inbox, raw=raw)
            except Refused as exc:
                if exc.status in (401, 403, 404):
                    inbox.record_connection("stopped", reason=str(exc))
                    raise ListenerStopped(self._stop_reason(exc)) from exc
                state = self._transient(inbox, exc, delay, state)
                sleep(delay)
                delay = min(delay * 2, 30.0)
                continue
            except (requests.RequestException, OSError, ValueError) as exc:
                state = self._transient(inbox, exc, delay, state)
                sleep(delay)
                delay = min(delay * 2, 30.0)
                continue
            if state != "connected":
                inbox.record_connection("connected", account=self.phone_number_id)
                inbox.log(f"polling O API for {self.phone_number_id}")
                state = "connected"
            delay = 1.0
            if not delivered:
                sleep(2.0)

    def _transient(self, inbox: Inbox, exc: Exception, delay: float, state):
        inbox.log(f"O API poll failed ({type(exc).__name__}: {self._redact(str(exc))}); "
                  f"retrying in {delay:.0f}s")
        if state != "disconnected":
            inbox.record_connection("disconnected", reason=self._redact(str(exc)))
        return "disconnected"

    @staticmethod
    def _stop_reason(exc: "Refused") -> str:
        if exc.status == 404:
            return (f"O API does not serve the WhatsApp Cloud inbox ({INBOX_ROUTE} is 404). "
                    f"The server side is openonion/oo-api#227; until it is deployed there is "
                    f"nothing to poll. Next: co whatsapp-cloud check")
        return f"{exc}. Next: co auth"

    def _poll_once(self, inbox: Inbox, *, raw: bool = False) -> int:
        """One claim. Each event is ACKed only after it is on disk."""
        page = self._o_api("post", INBOX_ROUTE, json={"limit": 20, "lease_seconds": 60})
        events = page.get("events") or []
        for event in events:
            try:
                message = self.to_message(event, raw=raw)
                accepted = inbox.deliver(message, raw=raw)
            except Exception as exc:
                # Not written, so not delivered: hand it back rather than let
                # the lease run out, so the retry is 30 seconds away and not 60.
                self._nack(event, type(exc).__name__)
                inbox.log(f"delivery {event.get('delivery_id', 'unknown')} not stored "
                          f"({type(exc).__name__}); returned to O API")
                continue
            self._ack(event)
            inbox.log(f"{'received' if accepted else 'duplicate'} {message.id} "
                      f"chat={message.chat} sender={message.sender}")
        return len(events)

    @staticmethod
    def to_message(event: dict, *, raw: bool = False) -> Message:
        """An O API messaging event as a Message.

        O API has already reduced Meta's payload to these fields; a direct
        chat is the only kind the Cloud API has, so every message is addressed
        to us and `chat` is the sender's number. Non-text messages arrive as
        text `[image]` and the like, which is O API's spelling today; `kind`
        is taken from the event when O API starts sending it.
        """
        required = ("id", "chat", "sender", "delivery_id", "lease_token")
        absent = [name for name in required if not event.get(name)]
        if absent:
            raise ValueError(f"O API returned a messaging event without {', '.join(absent)}")
        return Message(
            id=str(event["id"]),
            chat=str(event["chat"]),
            thread=event.get("thread") or None,
            sender=str(event["sender"]),
            sender_name=str(event.get("sender_name") or ""),
            text=str(event.get("text") or ""),
            kind=str(event.get("kind") or "text"),
            mentioned=bool(event.get("mentioned", True)),
            at=str(event.get("at") or iso_utc()),
            raw=dict(event) if raw else None,
        )

    def _ack(self, event: dict) -> None:
        self._o_api("post", f"/api/v1/messaging/inbox/{event['delivery_id']}/ack",
                    json={"lease_token": event["lease_token"]})

    def _nack(self, event: dict, error: str) -> None:
        self._o_api("post", f"/api/v1/messaging/inbox/{event['delivery_id']}/nack",
                    json={"lease_token": event["lease_token"], "error": error,
                          "retry_after_seconds": 30})

    # ---- outbound ----------------------------------------------------------

    def send(self, chat: str, text: str, *, reply_to: Optional[str] = None, fresh: bool = False,
             plain: bool = False) -> str:
        """Send text to a number, quoting `reply_to` when given. Returns the
        new message id. `fresh` is accepted so every provider takes the same
        arguments; Meta does not dedupe, so there is nothing for it to change."""
        body = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": chat,
            "type": "text",
            "text": {"preview_url": False, "body": text if plain else to_whatsapp(text)},
        }
        if reply_to:
            body["context"] = {"message_id": reply_to}
        return self._message_id(self._meta("post", f"/{self.phone_number_id}/messages", json=body))

    def react(self, chat: str, message_id: str, emoji: str, *, sender: str = "",
              mine: bool = False) -> str:
        """Put an emoji on a message; "" takes ours off. Same endpoint as a
        text, a different type."""
        body = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": chat,
            "type": "reaction",
            "reaction": {"message_id": message_id, "emoji": emoji},
        }
        return self._message_id(self._meta("post", f"/{self.phone_number_id}/messages", json=body))

    def render(self, text: str) -> str:
        """The characters WhatsApp will receive, given Markdown. The Cloud API
        reads the same marks as the app, so this is `co whatsapp`'s rendering."""
        return to_whatsapp(text)

    # ---- HTTP -------------------------------------------------------------

    def _o_api(self, method: str, path: str, **kwargs) -> dict:
        from ..backend import backend_url
        from ..credentials import require_ambient_api_key

        token = require_ambient_api_key()
        response = requests.request(method.upper(), f"{backend_url()}{path}",
                                    headers={"Authorization": f"Bearer {token}"},
                                    timeout=15, **kwargs)
        try:
            result = response.json()
        except ValueError:
            raise Refused(f"O API returned HTTP {response.status_code} without JSON",
                          response.status_code) from None
        if not 200 <= response.status_code < 300 or not isinstance(result, dict):
            detail = result.get("detail") if isinstance(result, dict) else None
            raise Refused(self._redact(f"O API refused ({response.status_code}): "
                                       f"{detail or 'no detail'}"), response.status_code)
        return result

    def _meta(self, method: str, path: str, **kwargs) -> dict:
        response = requests.request(method.upper(), f"{GRAPH}/{self.graph_version}{path}",
                                    headers={"Authorization": f"Bearer {self.access_token}"},
                                    timeout=15, **kwargs)
        try:
            result = response.json()
        except ValueError:
            raise RuntimeError(f"WhatsApp returned HTTP {response.status_code} without JSON") from None
        if 200 <= response.status_code < 300 and isinstance(result, dict):
            return result
        error = result.get("error") if isinstance(result, dict) else None
        error = error if isinstance(error, dict) else {}
        code = error.get("code")
        safe = self._redact(f"WhatsApp refused ({code or response.status_code}): "
                            f"{error.get('message') or 'request failed'}")
        if code == SERVICE_WINDOW_ERROR:
            raise ProviderPolicyError(
                f"{safe}. The 24-hour customer-service window is closed: this number may "
                f"only send a pre-approved template until they write again.")
        raise RuntimeError(safe)

    @staticmethod
    def _message_id(result: dict) -> str:
        messages = result.get("messages") or []
        if not messages or not messages[0].get("id"):
            raise RuntimeError("WhatsApp accepted the request but returned no message id")
        return str(messages[0]["id"])

    def _redact(self, value: str) -> str:
        """Provider errors sometimes echo the request. None of the four
        secrets may reach a terminal, a log, or sent.jsonl that way."""
        for secret in (self.access_token, os.environ.get("OPENONION_API_KEY", ""),
                       _env("APP_SECRET"), _env("VERIFY_TOKEN")):
            if secret:
                value = value.replace(secret, "[redacted]")
        return value[:1000]


def _env(key: str) -> str:
    return os.environ.get(f"{ENV}{key}", "").strip()
