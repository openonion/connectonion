"""A taken port is said before the banner, with how to pick another.

Found on 1.8.8b7 with a second `python agent.py` in the same project:

    [host] ───────────────────────────────────
           http://localhost:8000
           POST /input · WS /ws · GET /docs
           ...
    ERROR:    [Errno 48] error while attempting to bind on address
              ('0.0.0.0', 8000): address already in use

The banner announced an address this process would never serve, and the
error that followed named neither host.yaml nor AGENT_PORT.
"""

import socket

import pytest

from connectonion.network.host import server

# Taken at import, before tests/conftest.py stubs it out for every other host() test.
REAL_PORT_CHECK = server._port_in_use


@pytest.fixture
def taken_port():
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("0.0.0.0", 0))
    sock.listen(1)
    yield sock.getsockname()[1]
    sock.close()


@pytest.fixture
def project(tmp_path, monkeypatch, taken_port):
    from connectonion import address

    co = tmp_path / ".co"
    co.mkdir()
    address.save(address.generate(), co)
    (co / "host.yaml").write_text(f"name: t\nentrypoint: agent.py\nport: {taken_port}\n")
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("AGENT_PORT", raising=False)
    monkeypatch.setattr(server, "_port_in_use", REAL_PORT_CHECK)
    return tmp_path


def _host(monkeypatch):
    from connectonion import Agent
    from connectonion.network.host import server

    served = []
    monkeypatch.setattr(server.uvicorn, "run", lambda app, **kw: served.append(kw))
    with pytest.raises(SystemExit) as exit_info:
        server.host(Agent("t", tools=[], model="co/gemini-2.5-flash", api_key="k"),
                    relay_url=None)
    return exit_info.value, served


def test_it_stops_before_the_banner(project, taken_port, monkeypatch, capsys):
    _, served = _host(monkeypatch)
    captured = capsys.readouterr()

    assert served == []
    assert f"http://localhost:{taken_port}" not in captured.out


def test_it_says_which_port_and_how_to_change_it(project, taken_port, monkeypatch, capsys):
    error, _ = _host(monkeypatch)
    text = " ".join((str(error.code) + capsys.readouterr().out).split())

    assert str(taken_port) in text
    assert "already in use" in text
    assert "port:" in text and ".co/host.yaml" in text
    assert "AGENT_PORT=" in text


def test_a_free_port_is_not_reported(tmp_path):
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    free = sock.getsockname()[1]
    sock.close()

    assert REAL_PORT_CHECK(free) is False
