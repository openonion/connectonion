"""`co proxy` — lend this computer's internet connection to an authorized agent.

A browser on a server reaches the internet from a data-centre address. Sharing
this machine's connection makes it arrive from here instead, which is the whole
point of the Remote Browser product:

    browser on the host  ──▶  this machine  ──▶  the internet (your IP)

Every command here ends by naming the next one, because the caller is usually
an agent whose entire world is what it types and what comes back.
"""

from __future__ import annotations

import asyncio
import contextlib
import hmac
import json
import os
import secrets
import signal
import sys
import tempfile
import time
from pathlib import Path

USAGE = """co proxy — share this computer's internet connection.

  co proxy share [to <address>]   lend your connection to one agent
  co proxy status                 what is shared right now
  co proxy stop [<address>]       stop lending
  co proxy diagnose [<address>]   why a share is not working

<address> defaults to the one `co remote-browser config` remembered.

Options:
  --json          emit the complete stable JSON envelope
  --ttl SEC       stop sharing automatically after this long
  --bind HOST     address to listen on (default: the one a peer reaches)

Start with: co proxy share to 0xHOST"""

STATE_PATH = Path.home() / ".co" / "proxy-shares.json"


def _load() -> dict:
    if not STATE_PATH.exists():
        return {}
    return json.loads(STATE_PATH.read_text(encoding="utf-8"))


def _save(state: dict) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(
        prefix=f".{STATE_PATH.name}.", dir=STATE_PATH.parent
    )
    path = Path(temporary)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(state, stream, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        path.chmod(0o600)
        path.replace(STATE_PATH)
    finally:
        path.unlink(missing_ok=True)


def _emit(envelope: dict, as_json: bool) -> int:
    if as_json:
        print(json.dumps(envelope, indent=2))
    else:
        print(envelope["summary"], flush=True)
        for tip in envelope.get("next_actions", []):
            print(f"  {tip}", flush=True)
    return 0 if envelope["ok"] else 1


def _share(address: str, as_json: bool, bind: str | None, ttl: int | None) -> int:
    """Serve the share until the operator stops it.

    This command holds the process open on purpose. A share is a listening
    socket owned by this process: returning after printing "sharing" would
    close it the moment the shell got its prompt back, so the command would
    report success and leave nothing running. Background it with `&` or a
    supervisor if you want the shell back; `--ttl` stops it on a timer.
    """
    from ...network.proxy_egress import ProxyEgressService

    async def run() -> int:
        service = ProxyEgressService(bind_host=bind)
        endpoint = await service.start()
        stop = asyncio.Event()
        control_token = secrets.token_urlsafe(32)

        async def control(reader, writer):
            try:
                supplied = await asyncio.wait_for(reader.readline(), timeout=2)
                expected = (control_token + "\n").encode("ascii")
                if hmac.compare_digest(supplied, expected):
                    writer.write(b"OK\n")
                    await writer.drain()
                    stop.set()
                else:
                    writer.write(b"REFUSED\n")
                    await writer.drain()
            finally:
                writer.close()
                with contextlib.suppress(Exception):
                    await writer.wait_closed()

        controller = await asyncio.start_server(control, "127.0.0.1", 0)
        control_host, control_port = controller.sockets[0].getsockname()[:2]
        state = _load()
        state[address] = {
            "url": endpoint.url,
            "host": endpoint.host,
            "port": endpoint.port,
            "username": endpoint.username,
            "password": endpoint.password,
            "ttl": ttl,
            "control_host": control_host,
            "control_port": control_port,
            "control_token": control_token,
        }
        _save(state)
        _emit(
            {
                "ok": True,
                "command": "share",
                "summary": (
                    f"Sharing this computer's connection with {address} at "
                    f"{endpoint.url}. Traffic that agent's browser sends now "
                    "leaves from your address. Serving until you stop it."
                ),
                "result": {"address": address, "url": endpoint.url},
                "next_actions": [
                    "Check it is being used with: co proxy status",
                    f"Stop lending with: co proxy stop {address}",
                ],
            },
            as_json,
        )
        # A supervisor stops this with SIGTERM, not Ctrl-C, and a share that
        # outlives its process in the registry is a share every later command
        # reports as live while nothing listens.
        loop = asyncio.get_running_loop()
        for signal_name in ("SIGTERM", "SIGINT"):
            number = getattr(signal, signal_name, None)
            if number is not None:
                with contextlib.suppress(NotImplementedError):
                    loop.add_signal_handler(number, stop.set)
        try:
            await asyncio.wait_for(stop.wait(), timeout=ttl or None)
        except (asyncio.TimeoutError, KeyboardInterrupt, asyncio.CancelledError):
            pass
        finally:
            controller.close()
            await controller.wait_closed()
            await service.stop()
            remaining = _load()
            remaining.pop(address, None)
            _save(remaining)
        return 0

    try:
        return asyncio.run(run())
    except KeyboardInterrupt:
        print(f"Stopped sharing with {address}.")
        print("  Lend it again with: co proxy share to " + address)
        return 0


def _status(as_json: bool) -> int:
    state = _load()
    if not state:
        return _emit(
            {
                "ok": True,
                "command": "status",
                "summary": "You are not sharing this computer's connection with anyone.",
                "result": {"shares": []},
                "next_actions": ["Lend it to an agent with: co proxy share to 0xHOST"],
            },
            as_json,
        )
    return _emit(
        {
            "ok": True,
            "command": "status",
            "summary": f"Sharing with {len(state)} agent(s): "
            + ", ".join(f"{a} at {s['url']}" for a, s in state.items()),
            "result": {"shares": [{"address": a, **{"url": s["url"]}} for a, s in state.items()]},
            "next_actions": [
                f"Stop lending with: co proxy stop {next(iter(state))}",
                f"Investigate one with: co proxy diagnose {next(iter(state))}",
            ],
        },
        as_json,
    )


def _stop(address: str, as_json: bool) -> int:
    state = _load()
    if address not in state:
        return _emit(
            {
                "ok": False,
                "code": "SHARE_NOT_FOUND",
                "command": "stop",
                "summary": f"You are not sharing your connection with {address}.",
                "next_actions": ["See what is shared with: co proxy status"],
            },
            as_json,
        )
    share = state[address]

    async def stop_live_share() -> bool:
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(
                    share["control_host"], int(share["control_port"])
                ),
                timeout=2,
            )
            writer.write((share["control_token"] + "\n").encode("ascii"))
            await writer.drain()
            reply = await asyncio.wait_for(reader.readline(), timeout=2)
            writer.close()
            with contextlib.suppress(Exception):
                await writer.wait_closed()
            return reply == b"OK\n"
        except (KeyError, TypeError, ValueError, OSError, asyncio.TimeoutError):
            return False

    if not asyncio.run(stop_live_share()):
        return _emit(
            {
                "ok": False,
                "code": "SHARE_STOP_FAILED",
                "command": "stop",
                "summary": (
                    f"The share for {address} is recorded but its service did not "
                    "accept the stop request."
                ),
                "next_actions": [
                    f"Inspect it with: co proxy diagnose {address}",
                ],
            },
            as_json,
        )
    deadline = time.monotonic() + 5
    while address in _load() and time.monotonic() < deadline:
        time.sleep(0.05)
    if address in _load():
        return _emit(
            {
                "ok": False,
                "code": "SHARE_STOP_TIMEOUT",
                "command": "stop",
                "summary": f"The share for {address} accepted stop but is still shutting down.",
                "next_actions": ["Retry: co proxy status"],
            },
            as_json,
        )
    return _emit(
        {
            "ok": True,
            "command": "stop",
            "summary": f"Stopped sharing your connection with {address}.",
            "next_actions": ["See what is still shared with: co proxy status"],
        },
        as_json,
    )


def _diagnose(address: str, as_json: bool) -> int:
    from ...network.proxy_egress import local_egress_address

    state = _load()
    share = state.get(address)
    if share is None:
        return _emit(
            {
                "ok": False,
                "code": "SHARE_NOT_FOUND",
                "command": "diagnose",
                "summary": f"No share for {address}.",
                "next_actions": [f"Create one with: co proxy share to {address}"],
            },
            as_json,
        )
    reachable = local_egress_address()
    bound = share["url"].split("//", 1)[1].split(":")[0]
    return _emit(
        {
            "ok": True,
            "command": "diagnose",
            "summary": (
                f"Share for {address} listens on {share['url']}; a peer reaches this "
                f"machine at {reachable}."
                + (
                    ""
                    if bound == reachable
                    else "  The bound address differs, so a remote agent may not "
                    "reach it — rebind with --bind."
                )
            ),
            "result": {"url": share["url"], "reachable_address": reachable},
            "next_actions": [
                f"Rebind with: co proxy share to {address} --bind {reachable}",
                f"Stop lending with: co proxy stop {address}",
            ],
        },
        as_json,
    )


def handle_proxy(args) -> int:
    args = list(args)
    as_json = "--json" in args
    args = [a for a in args if a != "--json"]

    bind = None
    ttl = None
    for flag, setter in (("--bind", "bind"), ("--ttl", "ttl")):
        if flag in args:
            index = args.index(flag)
            if index + 1 >= len(args):
                print(f"{flag} needs a value.", file=sys.stderr)
                print("Start with: co proxy share to 0xHOST", file=sys.stderr)
                return 2
            value = args[index + 2 - 1]
            if setter == "bind":
                bind = value
            else:
                ttl = int(value)
            del args[index : index + 2]

    if not args:
        print(USAGE)
        return 0

    from .remote_browser_commands import NOT_CONFIGURED, configured_address

    verb, rest = args[0], args[1:]
    if verb == "status":
        return _status(as_json)
    if verb not in {"share", "stop", "diagnose"}:
        print(f"Unknown command: co proxy {verb}", file=sys.stderr)
        print(USAGE, file=sys.stderr)
        return 2

    # `share to <address>` reads as English; `share <address>` also works, and
    # no address at all means the one `co remote-browser config` remembered.
    if rest[:1] == ["to"]:
        rest = rest[1:]
    target = rest[0] if rest else configured_address()
    if not target:
        print(NOT_CONFIGURED, file=sys.stderr)
        return 2
    if verb == "share":
        return _share(target, as_json, bind, ttl)
    return (_stop if verb == "stop" else _diagnose)(target, as_json)

    print(f"Unknown command: co proxy {verb}", file=sys.stderr)
    print(USAGE, file=sys.stderr)
    return 2
