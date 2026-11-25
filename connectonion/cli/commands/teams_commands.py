"""
Purpose: `co teams` — check Microsoft Teams status, list and read chats, send messages, and list joined teams and channels (#1907)
LLM-Note:
  Dependencies: imports from [json, os, re, shlex, sys, tempfile, httpx, typer, cli/style.py, command_tips, gmail_listings, environment, useful_tools/teams.Teams] | imported by [cli/main.py] | tested by [tests/unit/test_teams.py]
  Data flow: chats, ls, teams and channels save 15-minute account-bound ID lists under ~/.co/teams-listings → read, send and channels resolve row numbers (or take full Graph IDs) → send previews target chat and text by default and posts to Graph only when --yes is passed
  State/Effects: list commands save ID-only row maps under ~/.co/teams-listings unless --json; send --yes posts one chat message as the signed-in user; all other commands are read-only
  Errors: personal Microsoft accounts (MSA tenant 9188040d-6c67-4c5b-b112-36a304b66dad), missing scopes and Graph failures print a concise recovery line on stderr and exit 1; unconfirmed sends never suggest blind retry
"""

from __future__ import annotations

import json
import os
import re
import shlex
import sys
import tempfile
from typing import Optional

import httpx
from rich.markup import escape

from ...environment import global_config_dir
from .. import style
from .command_tips import (
    _print_styled,
    mark_next_step_named,
    print_tip,
    selected_tip,
    success_tips_enabled,
)
from .gmail_listings import ListingError, resolve_reference, save_listing

LISTINGS = global_config_dir() / "teams-listings"
ROW = re.compile(r"#?[0-9]{1,4}")


def _teams():
    from ...useful_tools.teams import Teams
    return Teams()


def _account(client) -> str:
    """Bind row numbers to the selected Microsoft account."""
    from ...useful_tools.teams import _jwt_claims

    graph = getattr(client, "_graph", None)
    credentials = getattr(graph, "_credentials", None)
    if credentials is not None:
        email = credentials.get("EMAIL") or ""
        if email:
            return email
        claims = _jwt_claims(getattr(graph, "_access_token", None) or credentials.get("ACCESS_TOKEN"))
        for key in ("preferred_username", "upn", "oid"):
            if claims.get(key):
                return f"microsoft:{claims[key]}"
    identity = client._request_json("/me?$select=id").get("id")
    if not identity:
        raise ValueError("Cannot identify this Microsoft account. Next: co auth microsoft")
    return f"microsoft:{identity}"


def _store_rows(client, family: str, ids: list[str]) -> str:
    token = save_listing(LISTINGS, _account(client), family, ids, provider="teams")
    pointer = LISTINGS / f"last-{family}"
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="ascii",
            dir=LISTINGS,
            prefix=f".last-{family}-",
            delete=False,
        ) as stream:
            temporary = stream.name
            stream.write(token)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, pointer)
    finally:
        if temporary and os.path.exists(temporary):
            os.unlink(temporary)
    return token


def _resolve_row(client, value: str, family: str, listing: str | None) -> str:
    if not ROW.fullmatch(value):
        return value
    relist = "co teams teams" if family == "teams" else "co teams chats"
    if listing is None:
        try:
            with open(LISTINGS / f"last-{family}", "rb") as stream:
                listing = stream.read(65).decode("ascii").strip()
        except (OSError, UnicodeError):
            raise ValueError(f"No recent Teams {family} list. Next: {relist}") from None
    try:
        return resolve_reference(LISTINGS, value, _account(client), family, listing, provider="teams")
    except ListingError as error:
        raise ValueError(f"{error} Next: {relist}") from None


def _line(value: str) -> str:
    return " ".join(str(value).split())


def _listing_note(token: str) -> str:
    return f"Listing: {token} (15 min; optional --listing ID pins these rows)"


def _emit_tip(command: str, *, on_stderr: bool = False) -> None:
    if not on_stderr:
        print_tip(f"Next: {command}")
        return
    mark_next_step_named()
    if success_tips_enabled():
        _print_styled(f"Next: {selected_tip(command)}", stderr=True)


def _fail(message: str, next_command: str) -> None:
    err = style.console(stderr=True)
    clean = message.strip()
    if "\nNext:" in clean:
        cause, _, tail = clean.partition("\nNext:")
        next_command = tail.strip() or next_command
        clean = cause.strip()
    elif " Next: " in clean:
        cause, _, tail = clean.partition(" Next: ")
        next_command = tail.strip() or next_command
        clean = cause.strip()
    err.print(f"{style.error('✗')} {escape(clean)}")
    err.print(style.next_line(selected_tip(next_command)))
    mark_next_step_named()
    sys.exit(1)


def _run(
    call,
    *,
    retry_command: str,
    lookup_command: str = "co teams chats",
    write_target_chat: str | None = None,
) -> None:
    from ...credentials import AmbientCredentialError
    from ...environment import EnvironmentError
    from ...provider_credentials import ProviderCredentialError

    try:
        call(_teams())
    except httpx.TimeoutException:
        if write_target_chat:
            read_cmd = f"co teams read {shlex.quote(write_target_chat)}"
            _fail(
                "Microsoft Teams timed out after submitting the message. "
                "It may already have been delivered; inspect the chat before sending again.",
                read_cmd,
            )
        _fail("Microsoft Teams took too long to respond.", retry_command)
    except httpx.RequestError:
        if write_target_chat:
            read_cmd = f"co teams read {shlex.quote(write_target_chat)}"
            _fail(
                "Could not confirm whether Microsoft Teams delivered the message. "
                "It may already have been sent; inspect the chat before sending again.",
                read_cmd,
            )
        _fail("Could not reach Microsoft Teams. Check your connection.", retry_command)
    except OSError:
        _fail("Could not save or read the Teams row list under ~/.co.", lookup_command)
    except AmbientCredentialError as exc:
        _fail(str(exc), "co auth")
    except EnvironmentError as exc:
        _fail(str(exc), "co env")
    except ProviderCredentialError as exc:
        _fail(str(exc), exc.next_command or "co auth microsoft")
    except ValueError as exc:
        text = str(exc).strip()
        if "co auth microsoft" in text:
            _fail(text, "co auth microsoft")
        if write_target_chat and "may already have been" in text:
            _fail(text, f"co teams read {shlex.quote(write_target_chat)}")
        _fail(text, lookup_command)


def handle_teams_check(*, json_output: bool = False) -> None:
    def action(client) -> None:
        status = client.check()
        next_cmd = "co teams chats" if status.get("ok") else "co auth microsoft"
        if json_output:
            print(json.dumps(status, indent=2, ensure_ascii=False))
            _emit_tip(next_cmd, on_stderr=True)
            if not status.get("ok"):
                sys.exit(1)
            return

        scopes = status.get("scopes") or {}
        scope_parts = [f"{name} {'✓' if granted else '✗'}" for name, granted in scopes.items()]
        tenant_label = status.get("tenant_kind") or "unknown"
        if status.get("tenant_id"):
            tenant_label = f"{tenant_label} ({status['tenant_id']})"

        if not status.get("ok"):
            reason = status.get("reason") or "Microsoft Teams is not ready."
            detail = f"{reason}\n  Tenant: {tenant_label}\n  Scopes: {', '.join(scope_parts)}"
            _fail(detail, "co auth microsoft")

        out = style.console()
        who = status.get("email") or "connected account"
        token_state = (status.get("token") or {}).get("status") or "valid"
        out.print(f"{style.ok('✓')} Microsoft Teams: {escape(who)} ({escape(token_state)} token)")
        out.print(f"  Tenant: {escape(tenant_label)}")
        out.print(f"  Scopes: {escape(', '.join(scope_parts))}")
        _emit_tip("co teams chats")

    _run(action, retry_command="co teams check", lookup_command="co auth microsoft")


def handle_teams_chats(
    limit: int = 20,
    since: Optional[str] = None,
    *,
    unread_only: bool = False,
    show_ids: bool = False,
    json_output: bool = False,
) -> None:
    retry = "co teams chats"
    if since:
        retry += f" --since {shlex.quote(since)}"
    if unread_only:
        retry += " --unread"

    def action(client) -> None:
        chats = client.chat_items(limit=limit, since=since)
        if unread_only:
            chats = [chat for chat in chats if chat.get("unread")]

        if json_output:
            print(json.dumps(chats, indent=2, ensure_ascii=False))
            if chats:
                _emit_tip(f"co teams read {shlex.quote(chats[0]['id'])} --json", on_stderr=True)
            else:
                _emit_tip("co teams check", on_stderr=True)
            return

        ids = [chat["id"] for chat in chats]
        token = _store_rows(client, "chats", ids)
        if not chats:
            label = f" since {since}" if since else ""
            unread_word = " unread" if unread_only else ""
            print(f"No{unread_word} Teams chats found{label}.\n{_listing_note(token)}")
            _emit_tip("co teams teams")
            return

        lines = []
        for idx, chat in enumerate(chats, 1):
            badge = "[UNREAD] " if chat.get("unread") else ""
            title = _line(chat.get("title") or "(chat)")
            stamp = (chat.get("last_message_at") or "")[:16].replace("T", " ")
            row = f"{idx}. {badge}{title}"
            if stamp:
                row += f"  ({stamp})"
            if chat.get("preview"):
                sender = _line(chat.get("from") or "")
                prefix = f"{sender}: " if sender else ""
                row += f" — {prefix}{_line(chat['preview'])}"
            if show_ids:
                row += f"  (chat {chat['id']})"
            lines.append(row)
        lines.append(_listing_note(token))
        print("\n".join(lines))
        _emit_tip("co teams read 1")

    _run(action, retry_command=retry, lookup_command="co teams check")


def handle_teams_read(
    chat: Optional[str] = None,
    limit: int = 20,
    *,
    listing: Optional[str] = None,
    json_output: bool = False,
) -> None:
    if chat is None:
        handle_teams_chats(limit=limit, json_output=json_output)
        return

    retry = f"co teams read {shlex.quote(chat)}"
    if listing:
        retry += f" --listing {shlex.quote(listing)}"

    def action(client) -> None:
        resolved = _resolve_row(client, chat, "chats", listing)
        if json_output:
            messages = client.message_items(resolved, limit=limit)
            print(json.dumps(messages, indent=2, ensure_ascii=False))
            _emit_tip("co teams chats --json", on_stderr=True)
            return
        print(client.read_chat(resolved, limit=limit))
        _emit_tip("co teams chats")

    _run(action, retry_command=retry, lookup_command="co teams chats")


def handle_teams_send(
    chat: str,
    text: Optional[str] = None,
    *,
    listing: Optional[str] = None,
    yes: bool = False,
    json_output: bool = False,
) -> None:
    piped = text == "-" or (text is None and not sys.stdin.isatty())
    body = sys.stdin.read() if piped else (text or "")

    target_holder = [chat]

    def action(client) -> None:
        if not body.strip():
            raise ValueError("Message text cannot be empty. Next: co teams send --help")
        getattr(client, "_require_send_ready", lambda: None)()
        resolved = _resolve_row(client, chat, "chats", listing)
        target_holder[0] = resolved

        if not yes:
            json_flag = " --json" if json_output else ""
            if piped and ("\n" in body or "\r" in body or body == "-"):
                rerun = f"co teams send {shlex.quote(resolved)} - --yes{json_flag}"
                stdin_note = "Pipe the same message text on standard input when running with --yes."
            elif body.startswith("-"):
                rerun = f"co teams send {shlex.quote(resolved)} --yes{json_flag} -- {shlex.quote(body)}"
                stdin_note = None
            else:
                rerun = f"co teams send {shlex.quote(resolved)} {shlex.quote(body)} --yes{json_flag}"
                stdin_note = None

            if json_output:
                print(json.dumps(
                    {"preview": True, "sent": False, "chat_id": resolved, "text": body},
                    indent=2,
                    ensure_ascii=False,
                ))
                if stdin_note:
                    style.console(stderr=True).print(style.muted(escape(stdin_note)))
                _emit_tip(rerun, on_stderr=True)
                return

            out = style.console()
            out.print(f"{style.warn('Preview')} — message not sent (pass --yes to send):")
            out.print(f"  Chat:    {escape(resolved)}")
            out.print(f"  Message: {escape(body)}")
            if stdin_note:
                out.print(style.muted(escape(stdin_note)))
            _emit_tip(rerun)
            return

        if hasattr(client, "_send_message_item"):
            created = client._send_message_item(resolved, body)
        else:
            summary = client.send_message(resolved, body)
            created = {"id": "", "chatId": resolved, "summary": summary}

        read_next = f"co teams read {shlex.quote(resolved)}"
        if json_output:
            print(json.dumps(created, indent=2, ensure_ascii=False))
            _emit_tip(f"{read_next} --json", on_stderr=True)
            return

        msg_id = created.get("id") or ""
        out = style.console()
        suffix = f" ({escape(str(msg_id))})" if msg_id else ""
        out.print(f"{style.ok('✓')} Sent message{suffix} to chat {escape(resolved)}")
        _emit_tip(read_next)

    _run(
        action,
        retry_command=f"co teams read {shlex.quote(target_holder[0])}",
        lookup_command="co teams chats",
        write_target_chat=target_holder[0] if yes else None,
    )


def handle_teams_teams(*, show_ids: bool = False, json_output: bool = False) -> None:
    def action(client) -> None:
        teams = client.team_items()
        if json_output:
            print(json.dumps(teams, indent=2, ensure_ascii=False))
            if teams:
                _emit_tip(f"co teams channels {shlex.quote(teams[0]['id'])} --json", on_stderr=True)
            else:
                _emit_tip("co teams chats --json", on_stderr=True)
            return

        ids = [team["id"] for team in teams]
        token = _store_rows(client, "teams", ids)
        if not teams:
            print(f"No joined Teams found.\n{_listing_note(token)}")
            _emit_tip("co teams chats")
            return

        lines = []
        for idx, team in enumerate(teams, 1):
            name = _line(team.get("displayName") or "(untitled team)")
            desc = _line(team.get("description") or "")
            row = f"{idx}. {name}"
            if desc:
                row += f" — {desc}"
            if show_ids:
                row += f"  (team {team['id']})"
            lines.append(row)
        lines.append(_listing_note(token))
        print("\n".join(lines))
        _emit_tip("co teams channels 1")

    _run(action, retry_command="co teams teams", lookup_command="co teams check")


def handle_teams_channels(
    team: str,
    *,
    listing: Optional[str] = None,
    show_ids: bool = False,
    json_output: bool = False,
) -> None:
    from ...useful_tools.teams import CHANNEL_MESSAGE_ADMIN_NOTE

    retry = f"co teams channels {shlex.quote(team)}"
    if listing:
        retry += f" --listing {shlex.quote(listing)}"

    def action(client) -> None:
        resolved = _resolve_row(client, team, "teams", listing)
        channels = client.channel_items(resolved)
        if json_output:
            print(json.dumps(channels, indent=2, ensure_ascii=False))
            _emit_tip("co teams teams --json", on_stderr=True)
            return

        ids = [channel["id"] for channel in channels]
        token = _store_rows(client, "channels", ids)
        if not channels:
            print(f"No channels found in team {resolved}.\n{CHANNEL_MESSAGE_ADMIN_NOTE}\n{_listing_note(token)}")
            _emit_tip("co teams teams")
            return

        lines = []
        for idx, channel in enumerate(channels, 1):
            name = _line(channel.get("displayName") or "(untitled channel)")
            kind = _line(channel.get("membershipType") or "standard")
            row = f"{idx}. {name}  [{kind}]"
            if show_ids:
                row += f"  (channel {channel['id']})"
            lines.append(row)
        lines.append(CHANNEL_MESSAGE_ADMIN_NOTE)
        lines.append(_listing_note(token))
        print("\n".join(lines))
        _emit_tip("co teams chats")

    _run(action, retry_command=retry, lookup_command="co teams teams")
