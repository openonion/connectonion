"""Two conversations at once on a real Host never share an Agent's state.

`host(agent)` used to hand the same object to every request, and an Agent
keeps its turn in `self.current_session`, so two conversations running at the
same moment overwrote each other: one user's question vanished and the other
user's answer landed in their history. The `co create` template and `co ai`'s
own server both passed an instance.

Now `co ai` and the template pass a factory (a fresh Agent per request, run in
parallel), and a Host given an instance runs one turn at a time. Both are
driven here end to end: a real host() on a loopback port, two real
RemoteAgent clients with their own keys, asking at the same time.
"""

import threading
import time
from pathlib import Path

import pytest
import uvicorn

from connectonion import Agent, address
from connectonion.network.connect import RemoteAgent
from connectonion.network.host import server
from connectonion.network.host.session import SessionStorage
from tests.utils.mock_helpers import LLMResponseBuilder, MockLLM

WAIT = 15


def _free_port():
    import socket
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class LiveHost:
    def __init__(self, create_agent, co_dir: Path, monkeypatch):
        self.port = _free_port()
        co_dir.mkdir(exist_ok=True)
        if address.load(co_dir) is None:
            address.save(address.generate(), co_dir)
        self.address = address.load(co_dir)["address"]
        self.co_dir = co_dir
        started = threading.Event()

        def run(app, **kwargs):
            config = uvicorn.Config(app, host="127.0.0.1", port=self.port, log_level="warning",
                                    ws_max_size=kwargs.get("ws_max_size"))
            self._server = uvicorn.Server(config)
            started.set()
            self._server.run()

        monkeypatch.setattr(server.uvicorn, "run", run)
        self.thread = threading.Thread(target=server.host, args=(create_agent,), daemon=True, kwargs={
            "port": self.port, "trust": "open", "relay_url": None, "co_dir": co_dir})
        self.thread.start()
        assert started.wait(WAIT)
        deadline = time.monotonic() + WAIT
        while not self._server.started:
            assert time.monotonic() < deadline, "the Host did not start"
            time.sleep(0.02)

    def client(self):
        remote = RemoteAgent(self.address, keys=address.generate(), relay_url="ws://127.0.0.1:9")
        remote._endpoint_resolved = True
        remote._resolved_endpoint = f"ws://127.0.0.1:{self.port}/ws"
        return remote

    def stored(self, session_id):
        record = SessionStorage(self.co_dir / "session_results.jsonl").get(session_id)
        return [m.get("content") for m in record.session["messages"] if m["role"] in ("user", "assistant")]

    def stop(self):
        self._server.should_exit = True
        self.thread.join(WAIT)


class Model:
    """Answers each question by name. The first call waits briefly for a second
    call to arrive, so the test can see whether two turns ran at once."""

    def __init__(self):
        self.inside = 0
        self.overlapped = False
        self.second_arrived = threading.Event()
        self.lock = threading.Lock()
        self.calls = 0

    def __call__(self, messages, tools):
        question = [m for m in messages if m["role"] == "user"][-1]["content"]
        with self.lock:
            self.calls += 1
            first = self.calls == 1
            self.inside += 1
            if self.inside > 1:
                self.overlapped = True
                self.second_arrived.set()
        if first:
            self.second_arrived.wait(2)
        with self.lock:
            self.inside -= 1
        return LLMResponseBuilder.text_response(f"answer to {question}")


def ask_both(host):
    alice, bob = host.client(), host.client()
    answers = {}

    def ask(name, remote):
        answers[name] = remote.input(f"{name}'s question", timeout=WAIT)

    threads = [threading.Thread(target=ask, args=("alice", alice)),
               threading.Thread(target=ask, args=("bob", bob))]
    for thread in threads:
        thread.start()
        time.sleep(0.2)
    for thread in threads:
        thread.join(WAIT)
    return answers, alice, bob


@pytest.fixture
def start(own_project, monkeypatch):
    monkeypatch.setenv("AGENT_PUBLIC_DOMAIN", "agent.test")
    made = []

    def run(create_agent):
        host = LiveHost(create_agent, own_project / ".co", monkeypatch)
        made.append(host)
        return host

    yield run
    for host in made:
        host.stop()


def assert_apart(host, answers, alice, bob):
    assert answers["alice"].text == "answer to alice's question"
    assert answers["bob"].text == "answer to bob's question"
    assert host.stored(alice._session_id) == ["alice's question", "answer to alice's question"]
    assert host.stored(bob._session_id) == ["bob's question", "answer to bob's question"]


def test_a_factory_gives_each_conversation_its_own_agent_and_runs_them_together(start):
    model = Model()
    host = start(lambda: Agent("probe", system_prompt="You are Probe.", llm=MockLLM(on_complete=model), quiet=True))

    answers, alice, bob = ask_both(host)

    assert model.overlapped, "the two conversations did not run at the same time"
    assert_apart(host, answers, alice, bob)


def test_one_agent_object_runs_one_conversation_at_a_time(start):
    model = Model()
    shared = Agent("probe", system_prompt="You are Probe.", llm=MockLLM(on_complete=model), quiet=True)
    host = start(shared)

    answers, alice, bob = ask_both(host)

    assert not model.overlapped, "one Agent object ran two turns at once"
    assert_apart(host, answers, alice, bob)
