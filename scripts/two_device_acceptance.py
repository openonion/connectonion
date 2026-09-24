"""One conversation on a laptop and a phone at once, against a real Host (#1606).

    python scripts/two_device_acceptance.py                       # direct socket
    python scripts/two_device_acceptance.py --relay wss://oo.openonion.ai

Starts a real Host in a throwaway project (its own identity, trust: open, a
real model), then drives three clients whose frames are built and signed by
the real RemoteAgent code: a laptop and a phone holding the SAME identity — as
after importing the recovery phrase — and a stranger holding another. Nothing
is stubbed. Exit 0 only when every property below holds; the report says which
did not.

Costs a few cents of model calls. Through a relay the Host announces to it, so
the relay must be one that routes by connection (oo-api v0.1.19 or later).
"""

import argparse
import asyncio
import json
import os
import subprocess
import sys
import tempfile
import textwrap
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PORT = 8611

HOST = textwrap.dedent(f"""
    import sys
    from pathlib import Path
    from connectonion import Agent, address, host

    co = Path(".co")
    co.mkdir(exist_ok=True)
    if address.load(co) is None:
        address.save(address.generate(), co)
    (co / "host.yaml").write_text("trust: open\\nport: {PORT}\\nworkers: 1\\nresult_ttl: 3600\\nreload: false\\n")

    def lookup_flight(city: str) -> str:
        \"\"\"Look up the next flight to a city.\"\"\"
        return f"QF1 to {{city}} departs 09:30"

    agent = Agent("two-device-acceptance", tools=[lookup_flight],
                  system_prompt="Always call lookup_flight once, then answer in one short sentence.")
    host(agent, port={PORT}, relay_url=(sys.argv[1] if len(sys.argv) > 1 else None), co_dir=co)
""")


class Device:
    def __init__(self, name, keys, host_address, url, direct):
        from connectonion.network.connect import RemoteAgent

        self.name, self.url, self.direct, self.frames = name, url, direct, []
        self.client = RemoteAgent(host_address, keys=keys)

    async def open(self, session_id=None):
        import websockets

        self.ws = await websockets.connect(self.url, max_size=None)
        if session_id:
            self.client._current_session = {"session_id": session_id}
        await self.ws.send(json.dumps(self.client._build_connect_message(is_direct=self.direct)))
        while True:
            frame = json.loads(await asyncio.wait_for(self.ws.recv(), 60))
            if frame.get("type") == "ERROR":
                raise RuntimeError(f"{self.name}: {frame}")
            if frame.get("type") == "CONNECTED":
                self.session_id = frame["session_id"]
                break
        self.reader = asyncio.create_task(self._read())

    async def _read(self):
        async for raw in self.ws:
            frame = json.loads(raw)
            if frame.get("type") == "PING":
                await self.ws.send(json.dumps({"type": "PONG"}))
            else:
                self.frames.append(frame)

    async def ask(self, prompt):
        message = self.client._build_input_message(prompt, str(uuid.uuid4()), is_direct=self.direct)
        await self.ws.send(json.dumps(message))

    async def wait_for(self, kind, timeout=180):
        deadline = time.monotonic() + timeout
        while not self.of(kind):
            if time.monotonic() > deadline:
                raise TimeoutError(f"{self.name} never received {kind}")
            await asyncio.sleep(0.1)

    def of(self, kind):
        return [f for f in self.frames if f.get("type") == kind]


async def run(host_address, url, direct):
    from connectonion import address

    owner, other = address.generate(), address.generate()
    laptop, phone, stranger = (Device("laptop", owner, host_address, url, direct),
                               Device("phone", owner, host_address, url, direct),
                               Device("stranger", other, host_address, url, direct))
    await laptop.open()
    # A CONNECT signs {to, timestamp}: one identity connecting twice in the same
    # second sends the same bytes, which the replay ledger rightly refuses.
    await asyncio.sleep(1.2)
    await phone.open(laptop.session_id)
    await stranger.open(laptop.session_id)

    await laptop.ask("When is the next flight to Tokyo?")
    await laptop.wait_for("OUTPUT")
    await phone.wait_for("OUTPUT")
    first = {d.name: list(d.frames) for d in (laptop, phone, stranger)}
    for d in (laptop, phone):
        d.frames.clear()
    await phone.ask("And to Osaka?")
    await phone.wait_for("OUTPUT")
    await laptop.wait_for("OUTPUT")
    await asyncio.sleep(1)

    checks = {
        "the phone joined the laptop's session": phone.session_id == laptop.session_id,
        "a different identity was given its own session": stranger.session_id != laptop.session_id,
        "the phone saw the laptop's question": [f.get("content") for f in first["phone"]
                                                if f.get("type") == "user_message"]
        == ["When is the next flight to Tokyo?"],
        "the phone saw the tool call": any(f.get("type") == "tool_call" for f in first["phone"]),
        "both got the same answer": [f["result"] for f in first["laptop"] if f["type"] == "OUTPUT"]
        == [f["result"] for f in first["phone"] if f["type"] == "OUTPUT"],
        "the laptop was not echoed its own question": not any(
            f.get("type") == "user_message" for f in first["laptop"]),
        "the stranger received nothing of it": [f for f in stranger.frames + first["stranger"]
                                                if f.get("type") not in ("AGENT_PROFILE",
                                                                         "DASHBOARD_SNAPSHOT",
                                                                         "CONTROL_CENTER_STATE")] == [],
        "the laptop saw the phone's question": [f.get("content") for f in laptop.of("user_message")]
        == ["And to Osaka?"],
    }
    answer = [f["result"] for f in first["phone"] if f["type"] == "OUTPUT"]
    print(f"session   laptop {laptop.session_id}")
    print(f"          phone  {phone.session_id}")
    print(f"          other  {stranger.session_id}   (a different identity)")
    print(f"phone got user_message: {[f.get('content') for f in first['phone'] if f.get('type') == 'user_message']}")
    print(f"phone got answer:       {answer[0] if answer else None}")
    print(f"laptop got user_message: {[f.get('content') for f in laptop.of('user_message')]}")
    print(f"other got frames:       {len([f for f in stranger.frames if f.get('type') not in ('AGENT_PROFILE', 'DASHBOARD_SNAPSHOT', 'CONTROL_CENTER_STATE')])}")
    for name, ok in checks.items():
        print(f"{'✓' if ok else '✗'} {name}")
    for d in (laptop, phone, stranger):
        await d.ws.close()
    return all(checks.values())


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--relay", help="relay base URL, e.g. wss://oo.openonion.ai; direct socket if omitted")
    args = parser.parse_args()

    project = Path(tempfile.mkdtemp(prefix="two-device-"))
    (project / "host.py").write_text(HOST)
    env = {**os.environ, "PYTHONPATH": str(ROOT)}
    host = subprocess.Popen([sys.executable, "host.py", *([args.relay] if args.relay else [])],
                            cwd=project, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
    try:
        import httpx

        deadline = time.monotonic() + 60
        info = None
        while time.monotonic() < deadline and info is None:
            try:
                info = httpx.get(f"http://127.0.0.1:{PORT}/info", timeout=2).json()
            except httpx.HTTPError:
                time.sleep(0.5)
        if info is None:
            sys.exit("the Host did not start")
        if args.relay:
            time.sleep(5)  # its ANNOUNCE reaches the relay
            url, direct = f"{args.relay.rstrip('/')}/ws/input", False
        else:
            url, direct = f"ws://127.0.0.1:{PORT}/ws", True
        print(f"Host {info['address'][:12]}… via {'relay ' + args.relay if args.relay else 'direct socket'}")
        sys.exit(0 if asyncio.run(run(info["address"], url, direct)) else 1)
    finally:
        host.terminate()
        host.wait(10)


if __name__ == "__main__":
    main()
