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
import json
import sys
from pathlib import Path

USAGE = """co proxy — share this computer's internet connection.

  co proxy share to <address>     lend your connection to one agent
  co proxy status                 what is shared right now
  co proxy stop <address>         stop lending
  co proxy diagnose <address>     why a share is not working

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
    STATE_PATH.write_text(json.dumps(state, indent=2), encoding="utf-8")
    STATE_PATH.chmod(0o600)


def _emit(envelope: dict, as_json: bool) -> int:
    if as_json:
        print(json.dumps(envelope, indent=2))
    else:
        print(envelope["summary"])
        for tip in envelope.get("next_actions", []):
            print(f"  {tip}")
    return 0 if envelope["ok"] else 1


def _share(address: str, as_json: bool, bind: str | None, ttl: int | None) -> int:
    from ...network.proxy_egress import ProxyEgressService

    async def run() -> dict:
        service = ProxyEgressService(bind_host=bind)
        endpoint = await service.start()
        state = _load()
        state[address] = {
            "url": endpoint.url,
            "username": endpoint.username,
            "password": endpoint.password,
            "ttl": ttl,
        }
        _save(state)
        return {
            "ok": True,
            "command": "share",
            "summary": (
                f"Sharing this computer's connection with {address} at {endpoint.url}. "
                "Traffic that agent's browser sends now leaves from your address."
            ),
            "result": {"address": address, "url": endpoint.url},
            "next_actions": [
                "Check it is being used with: co proxy status",
                f"Stop lending with: co proxy stop {address}",
            ],
        }

    return _emit(asyncio.run(run()), as_json)


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
    state.pop(address)
    _save(state)
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

    verb, rest = args[0], args[1:]
    if verb == "share":
        # `share to <address>` reads as English; `share <address>` also works.
        target = rest[1] if rest[:1] == ["to"] else (rest[0] if rest else None)
        if not target:
            print("co proxy share needs an address.", file=sys.stderr)
            print("Try: co proxy share to 0xHOST", file=sys.stderr)
            return 2
        return _share(target, as_json, bind, ttl)
    if verb == "status":
        return _status(as_json)
    if verb in {"stop", "diagnose"}:
        if not rest:
            print(f"co proxy {verb} needs an address.", file=sys.stderr)
            print("See what is shared with: co proxy status", file=sys.stderr)
            return 2
        return (_stop if verb == "stop" else _diagnose)(rest[0], as_json)

    print(f"Unknown command: co proxy {verb}", file=sys.stderr)
    print(USAGE, file=sys.stderr)
    return 2
