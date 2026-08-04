"""Two keys in every host.yaml stop the agent from starting.

`.co/host.yaml` is generated with nine keys under "Host configuration — edit
these values". Two of them kill the agent:

    workers: 1     ->  2
    reload: false  ->  true

`host()` ends at

    uvicorn.run(app, host="0.0.0.0", port=port, workers=workers, reload=reload, ...)

and uvicorn can only fork workers or watch files if it is given an *import
string*. Handed an app object it refuses both, and `uvicorn.run` returns
without ever serving.

Measured, both through the code parameter and through host.yaml:

    [host] ───────────────────────────────────
           http://localhost:8794
           POST /input · WS /ws · GET /docs
           0xe8eab6d…
    WARNING:  You must pass the application as an import string to enable 'reload' or 'workers'.
    $ curl http://localhost:8794/info
    (nothing — the process is gone)

So the banner announces an address that answers nothing, and the only sign is
one uvicorn warning under it. Editing a documented value in the documented file
turns the agent off.

Serving them properly is a larger question than this: each worker process runs
its own scheduler loop and its own `in_flight` set, so a schedule that overruns
its interval gets one copy per worker — the race #537 is about. Until that is
answered, the honest thing is to keep the agent running and say what was not
honoured, rather than to exit behind a banner that says otherwise.
"""

import pytest

from connectonion.network.host.server import usable_uvicorn_options


class TestWhatUvicornCanActuallyBeGiven:

    def test_the_defaults_pass_through(self):
        assert usable_uvicorn_options(1, False) == (1, False)

    def test_more_than_one_worker_becomes_one(self):
        workers, _ = usable_uvicorn_options(4, False)

        assert workers == 1

    def test_reload_becomes_off(self):
        _, reload = usable_uvicorn_options(1, True)

        assert reload is False

    def test_both_at_once(self):
        assert usable_uvicorn_options(4, True) == (1, False)

    def test_zero_or_none_workers_is_one(self):
        """host.yaml is hand-edited; `workers:` with nothing after it is None."""
        assert usable_uvicorn_options(None, False)[0] == 1


class TestItSaysWhatItDidNotHonour:
    """Silently running one worker is a smaller lie than dying, but still a lie."""

    def test_dropping_workers_is_reported(self, capsys):
        usable_uvicorn_options(4, False)

        assert "workers" in capsys.readouterr().out

    def test_the_message_names_the_number_asked_for(self, capsys):
        usable_uvicorn_options(4, False)

        assert "4" in capsys.readouterr().out

    def test_dropping_reload_is_reported(self, capsys):
        usable_uvicorn_options(1, True)

        assert "reload" in capsys.readouterr().out

    def test_nothing_is_said_when_nothing_is_dropped(self, capsys):
        usable_uvicorn_options(1, False)

        assert capsys.readouterr().out == ""


class TestHostActuallyUsesIt:
    """A helper nothing calls is the bug, not the fix.

    This is the assertion that would have caught the original defect: it drives
    `host()` with the config that killed the agent and looks at what reaches
    uvicorn.
    """

    @pytest.fixture
    def project(self, tmp_path, monkeypatch):
        from connectonion import Agent, address

        co = tmp_path / ".co"
        co.mkdir()
        address.save(address.generate(), co)
        (co / "host.yaml").write_text(
            "name: t\nentrypoint: agent.py\nport: 8123\nworkers: 4\nreload: true\n")
        monkeypatch.chdir(tmp_path)
        return tmp_path

    def _run_host_capturing_uvicorn(self, monkeypatch):
        from connectonion import Agent
        from connectonion.network.host import server as server_module

        seen = {}
        monkeypatch.setattr(server_module.uvicorn, "run",
                            lambda app, **kw: seen.update(kw))

        server_module.host(Agent("t", tools=[], model="co/gemini-2.5-flash"),
                           relay_url=None)
        return seen

    def test_uvicorn_is_asked_for_one_worker(self, project, monkeypatch):
        assert self._run_host_capturing_uvicorn(monkeypatch)["workers"] == 1

    def test_uvicorn_is_asked_for_no_reload(self, project, monkeypatch):
        assert self._run_host_capturing_uvicorn(monkeypatch)["reload"] is False

    def test_it_still_serves_the_configured_port(self, project, monkeypatch):
        """The rest of host.yaml must keep working."""
        assert self._run_host_capturing_uvicorn(monkeypatch)["port"] == 8123
