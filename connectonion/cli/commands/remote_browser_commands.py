"""CLI for typed, owner-bound Remote Browser lifecycle commands."""

import json
import sys

USAGE = """co remote-browser — manage a browser session on a remote agent.

  co remote-browser [options] <address> start
  co remote-browser [options] <address> sessions
  co remote-browser [options] <address> status <session-id>
  co remote-browser [options] <address> stop <session-id>
  co remote-browser [options] <address> diagnose <session-id>

Options:
  --json           emit the complete stable JSON envelope
  --timeout SEC    seconds to wait (default 60)
  --relay URL      relay backend used for discovery/fallback
  --headless       start headless (default)
  --headed         start with a visible browser
  --proxy MODE     direct (this host's connection) or shared (yours)
"""


def _parse(args):
    options = {
        "json_output": False,
        "timeout": 60.0,
        "relay_url": None,
        "headless": True,
        "proxy": "direct",
    }
    positional = []
    index = 0
    while index < len(args):
        token = args[index]
        if token == "--json":
            options["json_output"] = True
        elif token == "--headless":
            options["headless"] = True
        elif token == "--headed":
            options["headless"] = False
        elif token in ("--timeout", "--relay", "--proxy"):
            if index + 1 >= len(args):
                raise ValueError(f"{token} needs a value")
            value = args[index + 1]
            index += 1
            if token == "--timeout":
                try:
                    options["timeout"] = float(value)
                except ValueError as exc:
                    raise ValueError("--timeout needs a number") from exc
                if options["timeout"] <= 0:
                    raise ValueError("--timeout must be positive")
            elif token == "--relay":
                options["relay_url"] = value
            else:
                options["proxy"] = value
        elif token.startswith("-"):
            raise ValueError(f"unknown option '{token}'")
        else:
            positional.append(token)
        index += 1
    return positional, options


def _print_human(result):
    if not result.get("ok"):
        code = result.get("code", "REMOTE_BROWSER_FAILED")
        message = result.get("message", "Remote Browser request failed.")
        print(f"{code}: {message}", file=sys.stderr)
        return
    print(result.get("summary", "Remote Browser request completed."))
    payload = result.get("result") or {}
    if "session_id" in payload:
        print(payload["session_id"])
    for session in payload.get("sessions", []):
        print(f"{session['session_id']}\t{session['status']}")


def _invalid_argument(message):
    return {
        "schema_version": "1",
        "ok": False,
        "command": "remote-browser",
        "request_id": "",
        "code": "INVALID_ARGUMENT",
        "message": message,
        "retryable": False,
        "retry_after_seconds": None,
        "state": {},
        "tips": [],
        "warnings": [],
        "next_actions": [],
    }


def _print_invalid_argument(message, *, json_output):
    if json_output:
        print(
            json.dumps(
                _invalid_argument(message), sort_keys=True, separators=(",", ":")
            )
        )
    else:
        print(f"usage: {message}", file=sys.stderr)
    return 2


def handle_remote_browser(args) -> int:
    args = list(args or [])
    json_requested = "--json" in args
    if not args:
        print(USAGE, file=sys.stderr)
        return 2
    if args[0] in ("help", "--help", "-h"):
        print(USAGE)
        return 0
    try:
        positional, options = _parse(args)
    except ValueError as exc:
        return _print_invalid_argument(str(exc), json_output=json_requested)

    if len(positional) < 2:
        return _print_invalid_argument(
            "co remote-browser <address> <command>",
            json_output=options["json_output"],
        )
    address, command, *rest = positional
    if command not in {"start", "status", "sessions", "stop", "diagnose"}:
        return _print_invalid_argument(
            f"unknown Remote Browser command '{command}'",
            json_output=options["json_output"],
        )
    needs_session = command in {"status", "stop", "diagnose"}
    if len(rest) != (1 if needs_session else 0):
        suffix = " <session-id>" if needs_session else ""
        return _print_invalid_argument(
            f"co remote-browser <address> {command}{suffix}",
            json_output=options["json_output"],
        )

    from connectonion import connect
    from connectonion.network.connect import _this_callers_identity

    connect_kwargs = {"keys": _this_callers_identity()}
    if options["relay_url"]:
        connect_kwargs["relay_url"] = options["relay_url"]
    command_args = {}
    if command == "start":
        command_args = {
            "headless": options["headless"],
            "proxy": options["proxy"],
        }
        if options["proxy"] == "shared":
            # Only this machine knows where its own connection is reachable, so
            # the share endpoint travels with the request rather than being
            # something the host could guess.
            from .proxy_commands import _load

            share = _load().get(address)
            if share is None:
                print(
                    f"You are not sharing your connection with {address}.",
                    file=sys.stderr,
                )
                print(f"Lend it with: co proxy share to {address}", file=sys.stderr)
                return 2
            command_args["share"] = share
    try:
        result = connect(address, **connect_kwargs).remote_browser(
            command,
            session_id=rest[0] if rest else None,
            timeout=options["timeout"],
            **command_args,
        )
    except Exception as exc:
        result = {
            "schema_version": "1",
            "ok": False,
            "command": f"remote-browser.{command}",
            "request_id": "",
            "code": "CONNECTION_FAILED",
            "message": str(exc),
            "retryable": True,
            "retry_after_seconds": None,
            "state": {},
            "tips": [],
            "warnings": [],
            "next_actions": [],
        }

    if options["json_output"]:
        print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    else:
        _print_human(result)
    return 0 if result.get("ok") else 1
