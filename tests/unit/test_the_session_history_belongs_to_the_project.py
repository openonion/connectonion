"""Hosting an agent from a subdirectory plants a `.co/` and loses its sessions.

`SessionStorage` defaults to a bare relative path, and its constructor creates
the directory:

    def __init__(self, path: str = ".co/session_results.jsonl"):
        self.path = Path(path)
        self.path.parent.mkdir(exist_ok=True)

`host()` constructs it with no argument, so this runs on the hosting path.
Measured on a project whose `.co/host.yaml` says `trust: strict`, from a
subdirectory of it, on main after #663:

    storage path      : .co/session_results.jsonl   (i.e. sub/.co/, not the project's)
    decoy .co created : True
    trust now reads   : None

Two costs. The session history is written somewhere no later run will look, so
an agent restarted from the project root does not see the turns it just served.
And the created `.co/` is a decoy: #660 and #661 made everything walk *up* to
the project, and the walk stops at the nearest `.co/`, so from then on the
subdirectory's empty one answers for `host.yaml` and the trust lists. A project
configured whitelist-only runs as `careful` — admitting contacts and accepting
invite codes — because of where the process was started.

#663 fixed the same shape in plan mode and in `co skills copy --to-project`.
This one was missed there: every test constructs `SessionStorage` with an
explicit path, so nothing exercised the default.

The path is also relative, so it is resolved afresh against the cwd on every
use — a tool that calls `os.chdir` moves the session history mid-run.
"""

from pathlib import Path

import pytest

from connectonion.network.host.session.storage import SessionStorage, Session


@pytest.fixture
def project(tmp_path):
    co = tmp_path / "project" / ".co"
    co.mkdir(parents=True)
    (co / "host.yaml").write_text("name: real\ntrust: strict\n")
    (tmp_path / "project" / "sub" / "deeper").mkdir(parents=True)
    return tmp_path / "project"


class TestFromASubdirectory:

    def test_no_decoy_is_created(self, project, monkeypatch):
        monkeypatch.chdir(project / "sub")

        SessionStorage()

        assert not (project / "sub" / ".co").exists(), "a decoy .co/ was planted"

    def test_the_history_goes_to_the_projects_co(self, project, monkeypatch):
        monkeypatch.chdir(project / "sub")

        assert Path(SessionStorage().path).parent == project / ".co"

    def test_the_configured_trust_still_reads(self, project, monkeypatch):
        """What the decoy costs: the project's own host.yaml stops being found."""
        from connectonion.network.host.config import load_host_config

        monkeypatch.chdir(project / "sub")
        SessionStorage()

        assert load_host_config(None).get("trust") == "strict"

    def test_a_saved_session_is_read_back_from_the_project_root(self, project, monkeypatch):
        """The other cost: a restart from the root must see what was served."""
        monkeypatch.chdir(project / "sub")
        SessionStorage().save(Session(session_id="s1", status="done", prompt="p"))

        monkeypatch.chdir(project)

        assert any(s.session_id == "s1" for s in SessionStorage().list())

    def test_two_levels_down_as_well(self, project, monkeypatch):
        monkeypatch.chdir(project / "sub" / "deeper")

        assert Path(SessionStorage().path).parent == project / ".co"


class TestThePathIsSettled(object):
    """A relative path is re-resolved on every use; a chdir moves the history."""

    def test_it_is_absolute(self, project, monkeypatch):
        monkeypatch.chdir(project)

        assert Path(SessionStorage().path).is_absolute()

    def test_a_chdir_after_construction_does_not_move_it(self, project, tmp_path, monkeypatch):
        monkeypatch.chdir(project)
        storage = SessionStorage()
        storage.save(Session(session_id="before", status="done", prompt="p"))

        elsewhere = tmp_path / "elsewhere"
        elsewhere.mkdir()
        monkeypatch.chdir(elsewhere)
        storage.save(Session(session_id="after", status="done", prompt="p"))

        ids = {s.session_id for s in storage.list()}
        assert ids == {"before", "after"}
        assert not (elsewhere / ".co").exists()


class TestWhatMustNotChange:

    def test_an_explicit_path_still_wins(self, project, tmp_path, monkeypatch):
        monkeypatch.chdir(project)
        chosen = tmp_path / "chosen" / "sessions.jsonl"
        chosen.parent.mkdir()

        assert Path(SessionStorage(chosen).path) == chosen

    def test_a_string_path_still_works(self, project, tmp_path, monkeypatch):
        monkeypatch.chdir(project)
        chosen = tmp_path / "chosen2"
        chosen.mkdir()

        SessionStorage(str(chosen / "s.jsonl")).save(Session(session_id="x", status="done", prompt="p"))

        assert (chosen / "s.jsonl").exists()

    def test_outside_any_project_it_still_works(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)

        storage = SessionStorage()
        storage.save(Session(session_id="loose", status="done", prompt="p"))

        assert (tmp_path / ".co").is_dir()
        assert any(s.session_id == "loose" for s in storage.list())


class TestHostUsesIt:
    """A default the hosting path does not reach would not be the bug."""

    def test_host_stores_sessions_in_the_projects_co(self, project, monkeypatch):
        from connectonion import Agent, address
        from connectonion.network.host import server as server_module

        address.save(address.generate(), project / ".co")
        monkeypatch.chdir(project / "sub")

        monkeypatch.setattr(server_module.uvicorn, "run", lambda app, **kw: None)
        monkeypatch.setattr(server_module, "_print_host_banner", lambda **kw: None)

        server_module.host(Agent("t", tools=[], model="co/gemini-2.5-flash",
                                 api_key="test-key"),
                           relay_url=None)

        assert not (project / "sub" / ".co").exists()


# Every entry point that a hosted agent touches early. This is the guard that
# catches the *next* one: #663 fixed two creators, this file is the third, and
# each was found only after the previous fix made the walk-up matter more.
# Subprocesses, because a decoy planted by one probe would hide the next.
IN_A_SUBDIRECTORY_OF_A_PROJECT = [
    ("session storage",
     "from connectonion.network.host.session.storage import SessionStorage; SessionStorage()"),
    ("an agent",
     "from connectonion import Agent; Agent('a', tools=[], model='co/gemini-2.5-flash')"),
    ("a logger",
     "from connectonion.logger import Logger; Logger(agent_name='a', quiet=True)"),
    ("a skill lookup",
     "from connectonion.useful_plugins.skills import _load_skill; _load_skill('x')"),
    ("a trust check",
     "from connectonion.network.trust.tools import get_level; get_level('0x'+'a'*64)"),
    ("the permission whitelist",
     "from connectonion.useful_plugins.tool_approval.approval import load_permission_patterns;"
     " load_permission_patterns(None)"),
]


class TestNothingPlantsADecoy:

    @pytest.mark.parametrize("what,probe",
                             IN_A_SUBDIRECTORY_OF_A_PROJECT,
                             ids=[w for w, _ in IN_A_SUBDIRECTORY_OF_A_PROJECT])
    def test_it_leaves_the_subdirectory_alone(self, what, probe, project):
        import os, subprocess, sys

        here = project / "sub"
        # This repo, not whatever `connectonion` happens to be installed. Without
        # it the probes import the released package and the test reports on that.
        env = dict(os.environ)
        repo = str(Path(__file__).resolve().parents[2])
        env["PYTHONPATH"] = repo + os.pathsep + env.get("PYTHONPATH", "")
        subprocess.run([sys.executable, "-c", probe], cwd=here, env=env,
                       capture_output=True, text=True, timeout=180, check=True)

        assert not (here / ".co").exists(), f"{what} planted a .co/ in {here}"
