"""WhatsApp Cloud API through O API ingress and direct Meta delivery."""

import os
import re
import time
from typing import Optional

import requests

from ..backend import backend_url
from ..credentials import require_ambient_api_key
from . import ProviderPolicyError
from .mailbox import Mailbox, Message, iso_utc


GRAPH = "https://graph.facebook.com"
_VERSION = re.compile(r"^v[0-9]+\.[0-9]+$")
SERVICE_WINDOW_ERROR = 131047


class WhatsApp:
    name = "whatsapp"

    def __init__(self):
        self.access_token = os.environ.get("WHATSAPP_ACCESS_TOKEN", "")
        self.phone_number_id = os.environ.get("WHATSAPP_PHONE_NUMBER_ID", "")
        self.binding_id = os.environ.get("WHATSAPP_BINDING_ID", "")
        self.graph_version = os.environ.get("WHATSAPP_GRAPH_VERSION", "")

    def missing(self) -> list[str]:
        problems = []
        if not os.environ.get("OPENONION_API_KEY"):
            problems.append("OPENONION_API_KEY is not set. Run 'co auth'.")
        if not self.binding_id:
            problems.append(
                "WHATSAPP_BINDING_ID is not set. Run 'co whatsapp bind' after "
                "creating the Meta app."
            )
        if not self.access_token:
            problems.append(
                "WHATSAPP_ACCESS_TOKEN is not set. Store the user-owned Cloud "
                "API token in ~/.co/keys.env."
            )
        if not self.phone_number_id:
            problems.append("WHATSAPP_PHONE_NUMBER_ID is not set.")
        if not _VERSION.fullmatch(self.graph_version):
            problems.append(
                "WHATSAPP_GRAPH_VERSION must be an explicit Meta version such "
                "as v23.0; pin a supported version rather than relying on latest."
            )
        return problems

    def bind_missing(self) -> list[str]:
        required = {
            "WHATSAPP_WABA_ID": os.environ.get("WHATSAPP_WABA_ID"),
            "WHATSAPP_PHONE_NUMBER_ID": self.phone_number_id,
            "WHATSAPP_APP_SECRET": os.environ.get("WHATSAPP_APP_SECRET"),
            "WHATSAPP_VERIFY_TOKEN": os.environ.get("WHATSAPP_VERIFY_TOKEN"),
            "OPENONION_API_KEY": os.environ.get("OPENONION_API_KEY"),
        }
        return [f"{name} is not set" for name, value in required.items() if not value]

    def bind(self) -> dict:
        token = require_ambient_api_key()
        response = requests.put(
            f"{backend_url()}/api/v1/messaging/bindings/whatsapp",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "waba_id": os.environ["WHATSAPP_WABA_ID"],
                "phone_number_id": self.phone_number_id,
                "app_secret": os.environ["WHATSAPP_APP_SECRET"],
                "verify_token": os.environ["WHATSAPP_VERIFY_TOKEN"],
            },
            timeout=15,
        )
        return self._o_api_result(response)

    def check(self) -> list[str]:
        problems = self.missing()
        if problems:
            return problems
        try:
            token = require_ambient_api_key()
            response = requests.get(
                f"{backend_url()}/api/v1/messaging/bindings",
                headers={"Authorization": f"Bearer {token}"},
                timeout=15,
            )
            bindings = self._o_api_result(response).get("bindings") or []
            if not any(str(row.get("id")) == self.binding_id for row in bindings):
                problems.append(
                    "WHATSAPP_BINDING_ID is not owned by this OpenOnion account"
                )
            graph = requests.get(
                f"{GRAPH}/{self.graph_version}/{self.phone_number_id}",
                params={"fields": "id"},
                headers={"Authorization": f"Bearer {self.access_token}"},
                timeout=15,
            )
            self._meta_result(graph)
        except Exception as exc:
            problems.append(f"WhatsApp check failed: {exc}")
        return problems

    def run(self, mailbox: Mailbox, *, raw: bool = False) -> None:
        delay = 1.0
        while True:
            try:
                delivered = self._poll_once(mailbox)
                delay = 1.0
                if not delivered:
                    time.sleep(2.0)
            except Exception as exc:
                mailbox.log(
                    f"O API poll {type(exc).__name__}; retrying in {delay:.0f}s"
                )
                time.sleep(delay)
                delay = min(delay * 2, 30.0)

    def _poll_once(self, mailbox: Mailbox) -> int:
        page = self._o_api(
            "post",
            "/api/v1/messaging/inbox/whatsapp/claim",
            json={"limit": 20, "lease_seconds": 60},
        )
        events = page.get("events") or []
        for event in events:
            try:
                message = self.to_message(event)
                accepted = mailbox.deliver(message)
            except Exception as exc:
                self._nack(event, type(exc).__name__)
                mailbox.log(
                    f"delivery {event.get('delivery_id', 'unknown')} could not be stored"
                )
                continue
            self._ack(event)
            status = "received" if accepted else "duplicate"
            mailbox.log(f"{status} {message.id} chat={message.chat} sender={message.sender}")
        return len(events)

    @staticmethod
    def to_message(event: dict) -> Message:
        required = ("id", "chat", "sender", "text", "delivery_id", "lease_token")
        if any(not event.get(name) for name in required):
            raise ValueError("O API returned an incomplete messaging event")
        return Message(
            id=str(event["id"]),
            chat=str(event["chat"]),
            thread=event.get("thread"),
            sender=str(event["sender"]),
            text=str(event["text"]),
            mentioned=bool(event.get("mentioned", True)),
            at=str(event.get("at") or iso_utc()),
        )

    def _ack(self, event: dict) -> None:
        self._o_api(
            "post",
            f"/api/v1/messaging/inbox/{event['delivery_id']}/ack",
            json={"lease_token": event["lease_token"]},
        )

    def _nack(self, event: dict, error: str) -> None:
        self._o_api(
            "post",
            f"/api/v1/messaging/inbox/{event['delivery_id']}/nack",
            json={
                "lease_token": event["lease_token"],
                "error": error,
                "retry_after_seconds": 30,
            },
        )

    def send(self, chat: str, text: str, *, reply_to: Optional[str] = None) -> str:
        body = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": chat,
            "type": "text",
            "text": {"preview_url": False, "body": text},
        }
        if reply_to:
            body["context"] = {"message_id": reply_to}
        response = requests.post(
            f"{GRAPH}/{self.graph_version}/{self.phone_number_id}/messages",
            headers={"Authorization": f"Bearer {self.access_token}"},
            json=body,
            timeout=15,
        )
        result = self._meta_result(response)
        messages = result.get("messages") or []
        if not messages or not messages[0].get("id"):
            raise RuntimeError("WhatsApp returned no message id")
        return str(messages[0]["id"])

    def _o_api(self, method: str, path: str, **kwargs) -> dict:
        token = require_ambient_api_key()
        response = getattr(requests, method)(
            f"{backend_url()}{path}",
            headers={"Authorization": f"Bearer {token}"},
            timeout=15,
            **kwargs,
        )
        return self._o_api_result(response)

    def _o_api_result(self, response) -> dict:
        try:
            result = response.json()
        except ValueError:
            raise RuntimeError(
                f"O API returned HTTP {response.status_code} without JSON"
            ) from None
        if not 200 <= response.status_code < 300 or not isinstance(result, dict):
            detail = result.get("detail") if isinstance(result, dict) else None
            raise RuntimeError(
                self._redact(f"O API refused: {detail or response.status_code}")
            )
        return result

    def _meta_result(self, response) -> dict:
        try:
            result = response.json()
        except ValueError:
            raise RuntimeError(
                f"WhatsApp returned HTTP {response.status_code} without JSON"
            ) from None
        error = result.get("error") if isinstance(result, dict) else None
        if not 200 <= response.status_code < 300 or not isinstance(result, dict):
            code = error.get("code") if isinstance(error, dict) else None
            message = error.get("message") if isinstance(error, dict) else None
            safe = self._redact(
                f"WhatsApp refused ({code or response.status_code}): "
                f"{message or 'request failed'}"
            )
            if code == SERVICE_WINDOW_ERROR:
                raise ProviderPolicyError(
                    safe
                    + "; the 24-hour customer-service window is closed and a "
                    "pre-approved template is required"
                )
            raise RuntimeError(safe)
        return result

    def _redact(self, value: str) -> str:
        secrets = (
            self.access_token,
            os.environ.get("OPENONION_API_KEY", ""),
            os.environ.get("WHATSAPP_APP_SECRET", ""),
            os.environ.get("WHATSAPP_VERIFY_TOKEN", ""),
        )
        for secret in secrets:
            if secret:
                value = value.replace(secret, "[redacted]")
        return value[:1000]
