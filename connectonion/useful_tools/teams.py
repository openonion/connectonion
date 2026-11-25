"""
Purpose: Microsoft Teams chats, teams and channels for agents and the CLI via Microsoft Graph (#1907)
LLM-Note:
  Dependencies: imports from [base64, datetime, html, json, re, urllib.parse, httpx, useful_tools/outlook.Outlook] | imported by [useful_tools/__init__.py, cli/commands/teams_commands.py] | requires work/school OAuth tokens from 'co auth microsoft' | tested by [tests/unit/test_teams.py]
  Data flow: Teams methods → _require_work_account() inspects JWT tenant claim before calling Graph and refuses personal Microsoft accounts (MSA tenant 9188040d-6c67-4c5b-b112-36a304b66dad or compact tickets) → _require_scope() checks delegated Teams scopes → JSON Graph calls go through Outlook's authenticated _request (token refresh, 429/503/504 GET retries, 429-only POST retry) → read_chat() converts HTML bodies to plain text in chronological order; send_message() posts plain text to /chats/{id}/messages
  State/Effects: reads MICROSOFT_* credentials | send_message() posts a message to an existing chat as the signed-in user; all other methods are read-only
  Integration: exposes Teams with check(), list_chats(limit, since), chat_items(limit, since), read_chat(chat_id, limit), message_items(chat_id, limit), send_message(chat_id, text), list_teams(), team_items(), list_channels(team_id), channel_items(team_id)
  Errors: ValueError naming 'co auth microsoft' when signed into a personal Microsoft account or missing the required Teams scope; transport timeouts on send_message() warn that the message may already have been delivered and never suggest blind retry

Microsoft Teams tool: check status, list and read chats, send messages, and list joined teams and channels.

Usage:
    from connectonion import Agent, Teams
    agent = Agent("teams-assistant", tools=[Teams()])
"""

from __future__ import annotations

import base64
from datetime import datetime, timedelta, timezone
import html
import json
import re
from urllib.parse import quote

import httpx

from .outlook import Outlook

# Microsoft's consumer tenant GUID for personal accounts (outlook.com, hotmail.com, live.com).
# Graph Teams chat and team APIs only support work or school Entra ID tenants.
MSA_TENANT_ID = "9188040d-6c67-4c5b-b112-36a304b66dad"

TEAMS_SCOPES = (
    "Chat.Read",
    "ChatMessage.Send",
    "Team.ReadBasic.All",
    "Channel.ReadBasic.All",
)

TIMEOUT = 60
NO_ANSWER = "Microsoft Teams did not answer within {seconds} s. Try again: {retry}"
UNCONFIRMED_SEND = (
    "Microsoft Teams did not confirm whether the message was sent. "
    "It may already have been delivered; inspect the chat before sending again: co teams read"
)
PERSONAL_ACCOUNT_REFUSAL = (
    f"Microsoft Teams Graph APIs require a work or school Microsoft account; "
    f"this sign-in is a personal Microsoft account (tenant {MSA_TENANT_ID}).\n"
    "Connect a work or school account:\n"
    "  co auth microsoft"
)
CHANNEL_MESSAGE_ADMIN_NOTE = (
    "Note: Channels are listed only; reading channel messages requires tenant admin consent "
    "(ChannelMessage.Read.All)."
)

_FRACTION = re.compile(r"\.(\d+)")
_WINDOW = re.compile(r"^(\d+)\s*([hdwmy])$", re.IGNORECASE)
_WINDOW_SECONDS = {
    "h": 3600,
    "d": 86400,
    "w": 7 * 86400,
    "m": 30 * 86400,
    "y": 365 * 86400,
}
_ISSUER_TENANT = re.compile(r"login\.microsoftonline\.com/([0-9a-fA-F-]{36})\b")


def _jwt_claims(token: str | None) -> dict:
    """Decode JWT payload claims without network calls, or {} for opaque tokens."""
    if not token or not isinstance(token, str) or token.count(".") != 2:
        return {}
    payload = token.split(".")[1]
    if not payload:
        return {}
    try:
        padded = payload + "=" * (-len(payload) % 4)
        decoded = json.loads(base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8"))
        return decoded if isinstance(decoded, dict) else {}
    except (ValueError, UnicodeDecodeError):
        return {}


def _tenant_from_token(token: str | None) -> tuple[str | None, str]:
    """Return (tenant_id, tenant_kind) where tenant_kind is work_or_school, personal, or unknown.

    Checks `tid` (the tenant being accessed, not `idp`, so B2B guests signed into
    a work tenant remain work_or_school), falls back to `iss`, and recognizes
    MSA consumer compact tickets (`Ew...`).
    """
    if not token or not isinstance(token, str):
        return None, "unknown"
    claims = _jwt_claims(token)
    tid = str(claims.get("tid") or "").strip()
    if not tid:
        issuer = str(claims.get("iss") or "").strip()
        matched = _ISSUER_TENANT.search(issuer)
        if matched:
            tid = matched.group(1)
    if tid:
        if tid.lower() == MSA_TENANT_ID:
            return MSA_TENANT_ID, "personal"
        return tid, "work_or_school"
    # Microsoft consumer STS issues compact tickets starting with "Ew" (no JWT dots)
    # exclusively for personal Microsoft accounts.
    if token.startswith("Ew") and "." not in token:
        return MSA_TENANT_ID, "personal"
    return None, "unknown"


def _parse_graph_dt(value: str | None) -> datetime | None:
    """Parse an ISO / Graph timestamp (including 7-digit fractional seconds) into UTC."""
    if not value or not isinstance(value, str):
        return None
    normalized = value.strip().replace("Z", "+00:00")
    normalized = _FRACTION.sub(lambda m: "." + (m.group(1) + "000000")[:6], normalized, count=1)
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _parse_since(value: str | datetime | None) -> datetime | None:
    """Parse a relative window (24h, 7d, 2w, 1m, 1y) or ISO date/datetime into UTC."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)
    text = str(value).strip()
    if not text:
        return None
    window = _WINDOW.fullmatch(text)
    if window:
        amount = int(window.group(1))
        if amount < 1:
            raise ValueError("Window in --since must be at least 1.")
        seconds = amount * _WINDOW_SECONDS[window.group(2).lower()]
        return datetime.now(timezone.utc) - timedelta(seconds=seconds)
    parsed = _parse_graph_dt(text)
    if parsed is None:
        raise ValueError(
            f"Cannot parse since value {value!r}. Use 24h, 7d, 2w, 1m, or an ISO date like 2026-11-20."
        )
    return parsed


def _safe_id(value: str, kind: str) -> str:
    """Validate and URL-quote a Graph resource identifier, rejecting path traversal."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{kind.capitalize()} ID cannot be empty.")
    cleaned = value.strip()
    if (
        cleaned in {".", ".."}
        or ".." in cleaned
        or any(ch in cleaned for ch in ("/", "\\", "?", "#"))
        or any(ch.isspace() or ord(ch) < 32 for ch in cleaned)
    ):
        raise ValueError(f"Invalid {kind} ID: {value!r}")
    return quote(cleaned, safe=":@!_-.")


def _body_to_text(
    body: dict | None,
    attachments: list | None = None,
    *,
    deleted: bool = False,
) -> str:
    """Convert a Graph chatMessage body (HTML or plain text) into clean plain text."""
    if deleted:
        return "[message deleted]"
    content = str((body or {}).get("content") or "")
    content_type = str((body or {}).get("contentType") or "text").strip().lower()

    if content_type == "html":
        text = re.sub(r"(?is)<(script|style)\b.*?</\1>", "", content)

        def _mention(match: re.Match) -> str:
            inner = html.unescape(re.sub(r"(?s)<[^>]+>", "", match.group(1))).strip()
            if not inner:
                return ""
            return inner if inner.startswith("@") else f"@{inner}"

        text = re.sub(r"(?is)<at\b[^>]*>(.*?)</at>", _mention, text)
        text = re.sub(r"(?is)<attachment\b[^>]*>.*?</attachment>", "", text)
        text = re.sub(r"(?is)<attachment\b[^>]*/?>", "", text)
        text = re.sub(r"(?is)<img\b[^>]*\balt=['\"]([^'\"]*)['\"][^>]*>", r"\n[image: \1]\n", text)
        text = re.sub(r"(?is)<img\b[^>]*>", "\n[image]\n", text)
        text = re.sub(r"(?is)</?(p|div|h[1-6]|li|br|tr|blockquote|pre)\b[^>]*>", "\n", text)
        text = html.unescape(re.sub(r"(?s)<[^>]+>", "", text)).replace("\xa0", " ").replace("\ufffc", "\n")
        lines = [line.strip() for line in text.splitlines() if line.strip()]
    else:
        cleaned = content.replace("\r\n", "\n").replace("\r", "\n").replace("\ufffc", "\n")
        lines = [line.rstrip() for line in cleaned.splitlines() if line.strip()]

    for attachment in attachments or []:
        if not isinstance(attachment, dict):
            continue
        label = (
            attachment.get("name")
            or attachment.get("contentType")
            or attachment.get("id")
            or "item"
        )
        lines.append(f"[attachment: {label}]")

    return "\n".join(lines)


def _sender_name(sender: dict | None) -> tuple[str, str | None]:
    """Return (display_name, sender_id) from a Graph chatMessage.from payload."""
    if not isinstance(sender, dict):
        return "Unknown", None
    for bucket in ("user", "application", "device"):
        actor = sender.get(bucket)
        if isinstance(actor, dict):
            name = str(actor.get("displayName") or "").strip()
            actor_id = actor.get("id")
            if name or actor_id:
                return name or str(actor_id), str(actor_id) if actor_id else None
    return "Unknown", None


class Teams:
    """Microsoft Teams chats, joined teams and channels for work or school accounts."""

    def __init__(self):
        # Composed with Outlook's credential record, token refresh and throttling
        # retries (never inherited, so an Agent given Teams() does not also get
        # Outlook's mail send/archive methods).
        self._graph = Outlook.__new__(Outlook)
        self._graph._access_token = None

    # ---- Auth & Graph -----------------------------------------------------

    def _granted_scopes(self, token: str | None = None) -> set[str]:
        credentials = self._graph._credentials
        raw = credentials.get("SCOPES") or ""
        granted = {s for s in raw.replace(",", " ").split() if s}
        claims = _jwt_claims(token or self._graph._access_token or credentials.get("ACCESS_TOKEN"))
        scp = claims.get("scp")
        if isinstance(scp, str) and scp.strip():
            granted.update(scp.split())
        roles = claims.get("roles")
        if isinstance(roles, list):
            granted.update(str(r) for r in roles if r)
        return granted

    @staticmethod
    def _scope_map(granted: set[str]) -> dict[str, bool]:
        return {
            "Chat.Read": "Chat.Read" in granted or "Chat.ReadWrite" in granted,
            "ChatMessage.Send": "ChatMessage.Send" in granted,
            "Team.ReadBasic.All": "Team.ReadBasic.All" in granted,
            "Channel.ReadBasic.All": "Channel.ReadBasic.All" in granted,
        }

    def _require_work_account(self) -> str:
        """Ensure credentials exist and belong to a work/school account before calling Graph."""
        credentials = self._graph._credentials
        cached = self._graph._access_token or credentials.get("ACCESS_TOKEN")
        if not (cached or credentials.get("REFRESH_TOKEN")):
            credentials.require_configured()

        if cached:
            _, kind = _tenant_from_token(cached)
            if kind == "personal":
                raise ValueError(PERSONAL_ACCOUNT_REFUSAL)

        token = self._graph._get_access_token()
        _, kind = _tenant_from_token(token)
        if kind == "personal":
            raise ValueError(PERSONAL_ACCOUNT_REFUSAL)
        return token

    def _require_scope(self, scope: str, token: str | None = None) -> None:
        granted = self._granted_scopes(token)
        satisfied = self._scope_map(granted).get(scope, scope in granted)
        if not satisfied:
            raise ValueError(
                f"Missing Microsoft {scope} scope: this sign-in did not grant it.\n"
                "Sign in again with a work or school account:\n"
                "  co auth microsoft"
            )

    def _require_send_ready(self) -> None:
        token = self._require_work_account()
        self._require_scope("ChatMessage.Send", token)

    def _request_json(self, endpoint: str, *, retry_command: str = "co teams chats", **kwargs) -> dict:
        try:
            return self._graph._request("GET", endpoint, timeout=TIMEOUT, **kwargs)
        except httpx.TransportError as error:
            raise ValueError(NO_ANSWER.format(seconds=TIMEOUT, retry=retry_command)) from error

    def _collect(
        self,
        endpoint: str,
        *,
        params: dict | None = None,
        limit: int | None = None,
        retry_command: str = "co teams chats",
    ) -> list[dict]:
        """Fetch one or more Graph pages, stopping at `limit` or when `@odata.nextLink` ends."""
        items: list[dict] = []
        next_endpoint: str | None = endpoint
        next_params = params
        seen_links: set[str] = set()

        while next_endpoint and (limit is None or len(items) < limit):
            page = self._request_json(next_endpoint, retry_command=retry_command,
                                      **({"params": next_params} if next_params else {}))
            batch = page.get("value") or []
            if isinstance(batch, list):
                items.extend(item for item in batch if isinstance(item, dict))
            raw_next = page.get("@odata.nextLink")
            if not isinstance(raw_next, str) or not raw_next or raw_next in seen_links:
                break
            seen_links.add(raw_next)
            if raw_next.startswith(Outlook.GRAPH_API_URL):
                next_endpoint = raw_next[len(Outlook.GRAPH_API_URL):]
            else:
                break
            next_params = None

        return items[:limit] if limit is not None else items

    # ---- Status -----------------------------------------------------------

    def check(self) -> dict:
        """Return structured status of token, tenant kind, and granted Teams scopes."""
        credentials = self._graph._credentials
        access_token = self._graph._access_token or credentials.get("ACCESS_TOKEN") or ""
        refresh_token = credentials.get("REFRESH_TOKEN") or ""
        configured = bool(access_token or refresh_token)

        expires_raw = credentials.get("TOKEN_EXPIRES_AT")
        expires_at = Outlook._parse_token_expiry(expires_raw)
        now = datetime.now(timezone.utc)
        claims = _jwt_claims(access_token)
        if expires_at is None and isinstance(claims.get("exp"), (int, float)):
            expires_at = datetime.fromtimestamp(float(claims["exp"]), tz=timezone.utc)

        if not configured:
            token_status = "missing"
        elif expires_at is not None and now >= expires_at:
            token_status = "expired_refreshable" if refresh_token else "expired"
        elif access_token:
            token_status = "valid"
        else:
            token_status = "refresh_only"

        tenant_id, tenant_kind = _tenant_from_token(access_token)
        granted = self._granted_scopes(access_token)
        scopes = self._scope_map(granted)
        missing_scopes = [name for name, ok in scopes.items() if not ok]
        email = (
            credentials.get("EMAIL")
            or claims.get("preferred_username")
            or claims.get("upn")
            or claims.get("unique_name")
            or None
        )

        ready = (
            configured
            and token_status not in ("missing", "expired")
            and tenant_kind != "personal"
            and scopes["Chat.Read"]
        )
        reason = None
        if not configured:
            reason = "Microsoft account is not connected. Run: co auth microsoft"
        elif tenant_kind == "personal":
            reason = (
                f"Personal Microsoft accounts (tenant {MSA_TENANT_ID}) are not supported by "
                "Microsoft Graph Teams APIs; sign in with a work or school account."
            )
        elif token_status == "expired":
            reason = "Microsoft access token is expired and has no refresh token. Run: co auth microsoft"
        elif not scopes["Chat.Read"]:
            reason = "Missing Microsoft Chat.Read scope. Run: co auth microsoft"

        return {
            "ok": ready,
            "email": email,
            "source": credentials.source,
            "token": {
                "configured": configured,
                "status": token_status,
                "has_access_token": bool(access_token),
                "has_refresh_token": bool(refresh_token),
                "expires_at": expires_raw,
            },
            "tenant_id": tenant_id,
            "tenant_kind": tenant_kind,
            "scopes": scopes,
            "missing_scopes": missing_scopes,
            "granted_scopes": sorted(granted),
            "reason": reason,
        }

    # ---- Chats ------------------------------------------------------------

    @staticmethod
    def _chat_dict(chat: dict) -> dict:
        raw_preview = chat.get("lastMessagePreview")
        preview: dict = raw_preview if isinstance(raw_preview, dict) else {}
        raw_viewpoint = chat.get("viewpoint")
        viewpoint: dict = raw_viewpoint if isinstance(raw_viewpoint, dict) else {}
        preview_time = preview.get("createdDateTime")
        read_time = viewpoint.get("lastMessageReadDateTime")
        preview_dt = _parse_graph_dt(preview_time)
        read_dt = _parse_graph_dt(read_time)

        if preview.get("isDeleted") or preview_dt is None:
            unread = False
        elif read_dt is None:
            unread = True
        else:
            unread = preview_dt > read_dt

        sender, _ = _sender_name(preview.get("from"))
        sender_label = "" if sender == "Unknown" else sender
        chat_type = str(chat.get("chatType") or "unknown")
        topic = str(chat.get("topic") or "").strip()
        if topic:
            title = topic
        elif chat_type == "oneOnOne" and sender_label:
            title = sender_label
        else:
            title = f"({chat_type} chat)"

        snippet_raw = _body_to_text(
            preview.get("body"),
            deleted=bool(preview.get("isDeleted")),
        )
        snippet = " ".join(snippet_raw.split())[:160]

        return {
            "id": str(chat.get("id") or ""),
            "topic": topic,
            "title": title,
            "chat_type": chat_type,
            "unread": unread,
            "last_message_at": str(preview_time or chat.get("lastUpdatedDateTime") or ""),
            "last_read_at": read_time,
            "from": sender_label,
            "preview": snippet,
            "web_url": str(chat.get("webUrl") or ""),
        }

    def chat_items(self, limit: int = 20, since: str | None = None) -> list[dict]:
        """List recent Teams chats as structured dicts, newest message first."""
        if limit < 1:
            raise ValueError("limit must be at least 1.")
        cutoff = _parse_since(since)
        token = self._require_work_account()
        self._require_scope("Chat.Read", token)

        page_size = min(int(limit), 50)
        params = {
            "$expand": "lastMessagePreview",
            "$orderby": "lastMessagePreview/createdDateTime desc",
            "$top": page_size,
        }

        collected: list[dict] = []
        next_endpoint: str | None = "/me/chats"
        next_params: dict | None = params
        seen_links: set[str] = set()

        while next_endpoint and len(collected) < limit:
            page = self._request_json(
                next_endpoint,
                retry_command="co teams chats",
                **({"params": next_params} if next_params else {}),
            )
            raw_chats = page.get("value") or []
            stop_paging = False
            for raw in raw_chats:
                if not isinstance(raw, dict):
                    continue
                item = self._chat_dict(raw)
                if cutoff is not None:
                    msg_dt = _parse_graph_dt(item["last_message_at"])
                    if msg_dt is None or msg_dt < cutoff:
                        stop_paging = True
                        continue
                collected.append(item)
                if len(collected) >= limit:
                    break
            if stop_paging or len(collected) >= limit:
                break
            raw_next = page.get("@odata.nextLink")
            if not isinstance(raw_next, str) or not raw_next or raw_next in seen_links:
                break
            seen_links.add(raw_next)
            if raw_next.startswith(Outlook.GRAPH_API_URL):
                next_endpoint = raw_next[len(Outlook.GRAPH_API_URL):]
            else:
                break
            next_params = None

        return collected

    def list_chats(self, limit: int = 20, since: str | None = None) -> str:
        """List recent Teams chats (1:1, group, meeting) with unread status and chat IDs."""
        chats = self.chat_items(limit=limit, since=since)
        if not chats:
            return f"No Teams chats found since {since}." if since else "No Teams chats found."
        lines = []
        for chat in chats:
            badge = "[UNREAD] " if chat["unread"] else ""
            stamp = (chat["last_message_at"] or "")[:16].replace("T", " ")
            meta = f" ({stamp})" if stamp else ""
            preview = ""
            if chat["preview"]:
                prefix = f"{chat['from']}: " if chat["from"] else ""
                preview = f" — {prefix}{chat['preview']}"
            lines.append(f"{badge}{chat['title']}{meta}{preview}  (chat {chat['id']})")
        return "\n".join(lines)

    # ---- Messages ---------------------------------------------------------

    def message_items(self, chat_id: str, limit: int = 20) -> list[dict]:
        """Fetch recent messages in a chat as structured dicts in chronological order."""
        if limit < 1:
            raise ValueError("limit must be at least 1.")
        safe_chat = _safe_id(chat_id, "chat")
        token = self._require_work_account()
        self._require_scope("Chat.Read", token)

        raw_messages = self._collect(
            f"/chats/{safe_chat}/messages",
            params={"$top": min(int(limit), 50)},
            limit=int(limit),
            retry_command=f"co teams read {chat_id}",
        )

        # Graph returns newest messages first; reverse and sort by timestamp for chronological reading.
        chronological = list(reversed(raw_messages))
        chronological.sort(
            key=lambda m: (
                _parse_graph_dt(m.get("createdDateTime")) or datetime.min.replace(tzinfo=timezone.utc)
            )
        )

        items: list[dict] = []
        for msg in chronological:
            deleted = bool(msg.get("deletedDateTime"))
            msg_type = str(msg.get("messageType") or "message")
            text = _body_to_text(msg.get("body"), msg.get("attachments"), deleted=deleted)
            if msg_type != "message" and not text:
                continue
            sender, sender_id = _sender_name(msg.get("from"))
            items.append({
                "id": str(msg.get("id") or ""),
                "created_at": str(msg.get("createdDateTime") or ""),
                "from": sender,
                "from_id": sender_id,
                "message_type": msg_type,
                "deleted": deleted,
                "text": text,
            })
        return items

    def read_chat(self, chat_id: str, limit: int = 20) -> str:
        """Read recent messages from one Teams chat as clean plain text, oldest first."""
        messages = self.message_items(chat_id, limit=limit)
        if not messages:
            return "No messages in this chat."
        lines = []
        for msg in messages:
            stamp = (msg["created_at"] or "")[:16].replace("T", " ")
            header = f"[{stamp}] {msg['from']}" if stamp else msg["from"]
            body_lines = (msg["text"] or "").splitlines() or [""]
            lines.append(f"{header}: {body_lines[0]}")
            for extra in body_lines[1:]:
                lines.append(f"  {extra}")
        return "\n".join(lines)

    def _send_message_item(self, chat_id: str, text: str) -> dict:
        """POST a plain-text message to an existing Teams chat and return Graph's response dict."""
        safe_chat = _safe_id(chat_id, "chat")
        if not isinstance(text, str) or not text.strip():
            raise ValueError("Message text cannot be empty.")
        token = self._require_work_account()
        self._require_scope("ChatMessage.Send", token)

        from ..provider_credentials import ProviderCredentialError
        try:
            return self._graph._request(
                "POST",
                f"/chats/{safe_chat}/messages",
                json={"body": {"contentType": "text", "content": text}},
                timeout=TIMEOUT,
            )
        except httpx.TransportError as error:
            raise ValueError(UNCONFIRMED_SEND) from error
        except ProviderCredentialError as error:
            if getattr(error, "status", None) in (502, 503, 504):
                raise ValueError(UNCONFIRMED_SEND) from error
            raise

    def send_message(self, chat_id: str, text: str) -> str:
        """Send a plain-text message to an existing Teams chat as the signed-in user."""
        created = self._send_message_item(chat_id, text)
        msg_id = created.get("id") or ""
        return f"Sent message {msg_id} to chat {chat_id}".strip()

    # ---- Joined Teams & Channels ------------------------------------------

    def team_items(self) -> list[dict]:
        """List joined Microsoft Teams as structured dicts."""
        token = self._require_work_account()
        self._require_scope("Team.ReadBasic.All", token)
        raw_teams = self._collect("/me/joinedTeams", retry_command="co teams teams")
        return [
            {
                "id": str(team.get("id") or ""),
                "displayName": str(team.get("displayName") or ""),
                "description": str(team.get("description") or ""),
                "isArchived": bool(team.get("isArchived", False)),
                "webUrl": str(team.get("webUrl") or ""),
            }
            for team in raw_teams
        ]

    def list_teams(self) -> str:
        """List the Microsoft Teams you have joined, with their team IDs."""
        teams = self.team_items()
        if not teams:
            return "No joined Teams found."
        lines = []
        for team in teams:
            name = team.get("displayName") or "(untitled team)"
            desc = f" — {team['description']}" if team.get("description") else ""
            lines.append(f"{name}{desc}  (team {team.get('id', '')})")
        return "\n".join(lines)

    def channel_items(self, team_id: str) -> list[dict]:
        """List channels in a joined team as structured dicts (metadata only)."""
        safe_team = _safe_id(team_id, "team")
        token = self._require_work_account()
        self._require_scope("Channel.ReadBasic.All", token)
        raw_channels = self._collect(
            f"/teams/{safe_team}/channels",
            retry_command=f"co teams channels {team_id}",
        )
        return [
            {
                "id": str(channel.get("id") or ""),
                "displayName": str(channel.get("displayName") or ""),
                "description": str(channel.get("description") or ""),
                "membershipType": str(channel.get("membershipType") or "standard"),
                "webUrl": str(channel.get("webUrl") or ""),
            }
            for channel in raw_channels
        ]

    def list_channels(self, team_id: str) -> str:
        """List channels of a joined team. Note: reading channel messages needs admin consent."""
        channels = self.channel_items(team_id)
        if not channels:
            return f"No channels found in team {team_id}.\n{CHANNEL_MESSAGE_ADMIN_NOTE}"
        lines = []
        for channel in channels:
            name = channel.get("displayName") or "(untitled channel)"
            kind = channel.get("membershipType") or "standard"
            lines.append(f"{name} [{kind}]  (channel {channel.get('id', '')})")
        lines.append(CHANNEL_MESSAGE_ADMIN_NOTE)
        return "\n".join(lines)
