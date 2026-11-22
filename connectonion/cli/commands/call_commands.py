"""
Purpose: `co call <address> <command...>` — run ONE command on a remote agent and print the result, no LLM.
LLM-Note:
  Dependencies: imports from [sys, shlex, base64, pathlib, connectonion.connect (RemoteAgent), connectonion.address (load local signing keys)] | imported by [cli/main.py via call()] | tested by [tests/unit/test_cli_call.py]
  Data flow: handle_call(args) → parse leading --out/--timeout/--relay options → first non-option token = address, everything after = the remote command VERBATIM → shlex.join → connect(address, keys).call("bash", command=...) → ExecResult → print text (or save an image result to --out / screenshot.png and print the path)
  State/Effects: signs with --co-dir/--global if given, else the project .co then ~/.co; names that address on stderr when it is not ~/.co and on every refusal | opens a WebSocket to the remote agent (direct or via relay) | may write an image file | writes to stdout/stderr
  Integration: exposes handle_call(args: list[str]) -> int (exit code) | mirrors handle_browser's thin-handler + exit-code contract (0 ok · 1 failure · 2 usage) | the remote symmetry of `co browser`: `co browser take_screenshot` locally == `co call <addr> co browser take_screenshot` remotely
  Performance: one WebSocket round-trip per call | endpoint resolution cached inside RemoteAgent for the process
  Errors: usage errors → stderr + exit 2 | connection/tool errors → stderr + exit 1 | the remote gates the command against ITS .co/host.yaml whitelist, so a non-whitelisted command comes back as an error result
"""

import shlex
import sys
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
    "  --relay URL       relay server (default: configured backend)\n"
    "  --global, -g      sign as your global identity (~/.co), not this project's\n"
    "  --co-dir DIR      sign with the key in DIR/keys\n"
    "\n"
    "Inside a project with its own .co/keys, co call signs as that project and\n"
    "says so on stderr; elsewhere it signs as ~/.co. A refusal names the address\n"
    "it signed with and where the key came from.\n"
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
    """This caller's identity, to sign the request.

    Every trust level above `open` refuses an unsigned request -- `careful`, the
    default, included. This was a second copy of the resolver that used a bare
    `Path(".co")`, so running `co call` from a subdirectory signed as the machine
    rather than as the project.
    """
    from connectonion.network.connect import _this_callers_identity

    return _this_callers_identity()


def _keys_in(co_dir):
    """The key in an explicitly chosen .co folder (--global or --co-dir)."""
    from connectonion import address

    return address.load(Path(co_dir))


def _is_global(keys) -> bool:
    """Whether these keys are the user's own ~/.co identity, not a project's."""
    from connectonion.environment import global_config_dir

    return Path(keys.get("source", global_config_dir())).resolve() == global_config_dir()


def _signed_as(keys) -> str:
    """One line naming who the remote saw: the address and the folder its key came from.

    A project's own .co/keys silently won over ~/.co, so a call that worked from
    ~ was refused as a stranger inside a project and nothing said why (#3182, #3298).
    """
    if not keys:
        return "sent unsigned: no .co/keys here or in ~/.co. Next: co init"
    line = f"signed as {keys.get('address')} from {keys.get('source')}/keys"
    if _is_global(keys):
        return line
    return f"{line} (this project's key; --global signs as your global identity)"


def _refused(message: str, signer: str) -> int:
    """Print why the call failed, then who signed it unless that was already said."""
    print(message, file=sys.stderr)
    if signer:
        print(signer, file=sys.stderr)
    return 1


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
    out, timeout, relay_url, co_dir = None, 60.0, None, None
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
        elif opt in ("--global", "-g"):
            from connectonion.environment import global_config_dir
            co_dir, i = global_config_dir(), i + 1
        elif opt == "--co-dir":
            if val is None:
                print("usage: --co-dir needs a .co folder", file=sys.stderr)
                return 2
            co_dir, i = Path(val).expanduser().resolve(), i + 2
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

    keys = _keys_in(co_dir) if co_dir else _load_keys()
    if co_dir and not keys:
        print(f"{co_dir} has no keys/agent.key. Next: co init, or pick another --co-dir",
              file=sys.stderr)
        return 2
    # Say who is calling once: up front for a project's key, else on a refusal.
    signer = _signed_as(keys)
    if keys and not _is_global(keys):
        print(signer, file=sys.stderr)
        signer = ""

    from connectonion import connect
    kwargs = {"keys": keys}
    if relay_url:
        kwargs["relay_url"] = relay_url

    try:
        remote = connect(address, **kwargs)
        result = remote.call("bash", command=command, timeout=timeout)
    except Exception as e:
        return _refused(f"connection failed: {e}", signer)

    if not result.ok:
        return _refused(result.error or "remote call failed", signer)

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

    # `--out` only applies to an image result, which the usage text says. What it
    # did not say is what happens without one: the option was dropped in silence,
    # so `co call --out result.txt <addr> co status` — which reads like "save the
    # output to a file" — produced no file and no explanation. Measured against a
    # real agent: text printed, exit 0, nothing at the path.
    #
    # stderr, not stdout: stdout is the result, per this module's contract. Exit
    # stays 0 because the call succeeded; only the save did not apply. And the
    # text is not written to the path — putting it in a .png would be worse than
    # not writing.
    if out:
        print(f"--out {out}: not written — the result is text, not an image "
              f"(--out saves a screenshot)", file=sys.stderr)

    print(result.text)
    return 0
