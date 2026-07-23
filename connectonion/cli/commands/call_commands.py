"""
Purpose: `co call <address> <command...>` — run ONE command on a remote agent and print the result, no LLM.
LLM-Note:
  Dependencies: imports from [sys, shlex, base64, pathlib, connectonion.connect (RemoteAgent), connectonion.address (load local signing keys)] | imported by [cli/main.py via call()] | tested by [tests/unit/test_cli_call.py]
  Data flow: handle_call(args) → parse leading --out/--timeout/--relay options → first non-option token = address, everything after = the remote command VERBATIM → shlex.join → connect(address, keys).call("bash", command=...) → ExecResult → print text (or save an image result to --out / screenshot.png and print the path)
  State/Effects: loads local identity from .co (project) then ~/.co to sign the request | opens a WebSocket to the remote agent (direct or via relay) | may write an image file | writes to stdout/stderr
  Integration: exposes handle_call(args: list[str]) -> int (exit code) | mirrors handle_browser's thin-handler + exit-code contract (0 ok · 1 failure · 2 usage) | the remote symmetry of `co browser`: `co browser take_screenshot` locally == `co call <addr> co browser take_screenshot` remotely
  Performance: one WebSocket round-trip per call | endpoint resolution cached inside RemoteAgent for the process
  Errors: usage errors → stderr + exit 2 | connection/tool errors → stderr + exit 1 | the remote gates the command against ITS .co/host.yaml whitelist, so a non-whitelisted command comes back as an error result
"""

import sys
import shlex
from pathlib import Path

USAGE = (
    "co call — run one command on a remote agent, print the result (no LLM).\n"
    "\n"
    "  co call [options] <address> <command...>\n"
    "\n"
    "  co call 0x3d40... co status\n"
    "  co call 0x3d40... co browser go_to https://example.com\n"
    "  co call --out shot.png 0x3d40... co browser take_screenshot\n"
    "\n"
    "Options (before the address):\n"
    "  --out PATH        save an image result (screenshot) to PATH; else ./screenshot.png\n"
    "  --timeout SEC     seconds to wait for the result (default 60)\n"
    "  --relay URL       relay server (default wss://oo.openonion.ai)\n"
    "\n"
    "Everything AFTER the address is the remote command, verbatim. It runs on the\n"
    "remote agent, gated by ITS .co/host.yaml permission whitelist — `co ...`\n"
    "(including `co browser <verb>`) is whitelisted by default.\n"
    "\n"
    "This is the remote twin of `co browser`: `co browser take_screenshot` here ==\n"
    "`co call <address> co browser take_screenshot` there.\n"
    "\n"
    "stdout = result, stderr = errors; exit 0 ok · 1 failure · 2 usage."
)


def _load_keys():
    """This machine's identity, to sign the request (required for strict-trust
    remotes, harmless otherwise). Project .co first, then ~/.co; None if absent."""
    from connectonion import address
    co_dir = Path(".co")
    if not (co_dir.exists() and (co_dir / "keys" / "agent.key").exists()):
        co_dir = Path.home() / ".co"
    return address.load(co_dir)


def handle_call(args) -> int:
    """Send one command to a remote agent's direct-exec path, print the result.

    Returns the process exit code (0 ok · 1 failure · 2 usage). Everything after
    the address is forwarded verbatim, so the remote command keeps its own flags.
    """
    args = list(args or [])
    if not args:
        print(USAGE, file=sys.stderr)
        return 2
    if args[0] in ("help", "--help", "-h"):
        print(USAGE)
        return 0

    # Consume leading local options; stop at the first non-flag token (the address).
    out, timeout, relay_url = None, 60.0, None
    i = 0
    while i < len(args) and args[i].startswith("-"):
        opt = args[i]
        val = args[i + 1] if i + 1 < len(args) else None
        if opt in ("--out", "-o"):
            if val is None:
                print("usage: --out needs a path", file=sys.stderr)
                return 2
            out, i = val, i + 2
        elif opt == "--timeout":
            if val is None:
                print("usage: --timeout needs seconds", file=sys.stderr)
                return 2
            try:
                timeout = float(val)
            except ValueError:
                print("usage: --timeout needs a number", file=sys.stderr)
                return 2
            i += 2
        elif opt == "--relay":
            if val is None:
                print("usage: --relay needs a url", file=sys.stderr)
                return 2
            relay_url, i = val, i + 2
        else:
            print(f"unknown option '{opt}' (options go before the address)", file=sys.stderr)
            return 2

    rest = args[i:]
    if not rest:
        print("usage: co call <address> <command...>", file=sys.stderr)
        return 2
    address = rest[0]
    command_tokens = rest[1:]
    if not command_tokens:
        print("usage: co call <address> <command...>  e.g. co call 0x.. co browser take_screenshot",
              file=sys.stderr)
        return 2
    command = shlex.join(command_tokens)

    from connectonion import connect
    kwargs = {"keys": _load_keys()}
    if relay_url:
        kwargs["relay_url"] = relay_url

    try:
        remote = connect(address, **kwargs)
        result = remote.call("bash", command=command, timeout=timeout)
    except Exception as e:
        print(f"connection failed: {e}", file=sys.stderr)
        return 1

    if not result.ok:
        print(result.error or "remote call failed", file=sys.stderr)
        return 1

    # An image result (a screenshot) is base64 — writing it to the terminal would
    # flood it, so save to a file and print the path (script-friendly).
    if result.images:
        import base64
        data = result.images[0]
        payload = data.split(",", 1)[1] if "," in data else data
        dest = out or "screenshot.png"
        Path(dest).write_bytes(base64.b64decode(payload))
        print(dest)
        return 0

    print(result.text)
    return 0
