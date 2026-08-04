"""The admin routes, the slash commands and the agent's own email address
answer for the directory the process was started in.

Four readers left on a bare relative path after #660, #661, #663 and #666:

    http_router.admin_logs_handler       Path(f".co/logs/{agent_name}.log")
    http_router.admin_sessions_handler   Path(".co/evals")
    slash_command.SlashCommand           Path(".co/commands"), Path("commands")
    send_email.get_agent_email           Path(".co") or Path("../.co")

Measured on a project holding one of each, from the project root and from two
depths below it:

                        root    sub     sub/deeper
    /admin/sessions     1       0       0
    logs found          True    False   False
    agent email         set     set     None
    slash cmd found     True    False   False

The first two are served over HTTP by the hosted agent: an operator looking at
Home sees no sessions and "No logs found" for an agent that has both.

`get_agent_email` is the interesting row. Someone already knew the walk was
needed and wrote one level of it:

    co_dir = Path(".co")
    if not co_dir.exists():
        co_dir = Path("../.co")

So it survives one subdirectory and fails at two — which is why the table above
measures two depths rather than one. That is the same walk `connectonion/project.py`
now does properly, for any depth.

All four fail in the visible direction — nothing is served from the wrong
project, it is simply absent — which is why they are being fixed rather than
filed: 1.6.0 is long-term support, and these are the last of the family.

Not changed here: `Path("commands")` for built-in commands. No `commands/`
directory ships in the package and there is none at the repo root, so "built-in"
in this class means a directory in the project rather than one in the install.
That reading is preserved — the directory is now found from a subdirectory like
everything else — but whether built-ins were meant to ship with the package is a
question this test cannot answer.
"""

from pathlib import Path

import pytest


@pytest.fixture
def project(tmp_path):
    """A project with a log, an eval, a custom command and an email configured."""
    root = tmp_path / "project"
    co = root / ".co"
    (co / "logs").mkdir(parents=True)
    (co / "evals").mkdir()
    (co / "commands").mkdir()
    (root / "commands").mkdir()
    (co / "host.yaml").write_text("agent:\n  email: a@mail.openonion.ai\n")
    (co / "logs" / "myagent.log").write_text("a log line\n")
    (co / "evals" / "s1.yaml").write_text("session_id: s1\n")
    (co / "commands" / "mycmd.md").write_text(
        "---\nname: mycmd\ndescription: mine\n---\n\ndo the thing\n")
    (root / "commands" / "builtin.md").write_text(
        "---\nname: builtin\ndescription: theirs\n---\n\nbuilt in\n")
    (root / "sub" / "deeper").mkdir(parents=True)
    return root


DEPTHS = ["sub", "sub/deeper"]


class TestTheAdminRoutes:
    """Served over HTTP by the hosted agent."""

    @pytest.mark.parametrize("depth", DEPTHS)
    def test_the_sessions_are_listed(self, project, monkeypatch, depth):
        from connectonion.network.host.http_router import admin_sessions_handler

        monkeypatch.chdir(project / depth)

        assert len(admin_sessions_handler().get("sessions", [])) == 1

    @pytest.mark.parametrize("depth", DEPTHS)
    def test_the_log_is_found(self, project, monkeypatch, depth):
        """Through the route, because the path now comes from the Logger.

        `admin_logs_handler` used to rebuild the path from the agent's display
        name and this asserted that rebuild resolved to the project. It takes
        the path itself now — the logger's, which walks up on its own (#661) —
        so the subdirectory case belongs at the route, where the two meet.
        """
        from connectonion import Agent
        from connectonion.network.host.server import _create_route_handlers
        from connectonion.network.trust.trust_agent import TrustAgent

        monkeypatch.chdir(project / depth)
        agent = Agent("myagent", tools=[], model="co/gemini-2.5-flash")
        handlers = _create_route_handlers(
            lambda: agent, {"name": "the-project"}, 3600, TrustAgent("careful"), {})

        assert "a log line" in handlers["admin_logs"]().get("content", "")


class TestTheAgentsOwnEmail:
    """One level of the walk was written by hand; this needs all of it."""

    @pytest.mark.parametrize("depth", DEPTHS)
    def test_it_is_configured(self, project, monkeypatch, depth):
        from connectonion.useful_tools.send_email import get_agent_email

        monkeypatch.chdir(project / depth)

        assert get_agent_email() == "a@mail.openonion.ai"


class TestTheSlashCommands:

    @pytest.mark.parametrize("depth", DEPTHS)
    def test_a_custom_command_loads(self, project, monkeypatch, depth):
        from connectonion.useful_tools.slash_command import SlashCommand

        monkeypatch.chdir(project / depth)

        assert SlashCommand.load("mycmd") is not None

    @pytest.mark.parametrize("depth", DEPTHS)
    def test_it_is_reported_as_custom(self, project, monkeypatch, depth):
        from connectonion.useful_tools.slash_command import SlashCommand

        monkeypatch.chdir(project / depth)

        assert SlashCommand.is_custom("mycmd")

    @pytest.mark.parametrize("depth", DEPTHS)
    def test_all_of_them_are_listed(self, project, monkeypatch, depth):
        from connectonion.useful_tools.slash_command import SlashCommand

        monkeypatch.chdir(project / depth)
        names = SlashCommand.list_all()

        assert "mycmd" in names and "builtin" in names


class TestFromTheProjectRoot:
    """Unchanged — all of this already worked."""

    def test_the_sessions_are_still_listed(self, project, monkeypatch):
        from connectonion.network.host.http_router import admin_sessions_handler

        monkeypatch.chdir(project)

        assert len(admin_sessions_handler().get("sessions", [])) == 1

    def test_the_email_is_still_read(self, project, monkeypatch):
        from connectonion.useful_tools.send_email import get_agent_email

        monkeypatch.chdir(project)

        assert get_agent_email() == "a@mail.openonion.ai"

    def test_a_custom_command_still_overrides_a_built_in(self, project, monkeypatch):
        """The precedence the class exists to express."""
        from connectonion.useful_tools.slash_command import SlashCommand

        (project / "commands" / "mycmd.md").write_text(
            "---\nname: mycmd\ndescription: theirs\n---\n\nthe built-in one\n")
        monkeypatch.chdir(project)

        assert SlashCommand.is_custom("mycmd")


class TestOutsideAnyProject:
    """No `.co/` above — each must still behave, not raise."""

    def test_no_sessions_rather_than_an_error(self, tmp_path, monkeypatch):
        from connectonion.network.host.http_router import admin_sessions_handler

        monkeypatch.chdir(tmp_path)

        assert admin_sessions_handler() == {"sessions": []}

    def test_no_logs_rather_than_an_error(self, tmp_path, monkeypatch):
        from connectonion.network.host.http_router import admin_logs_handler

        monkeypatch.chdir(tmp_path)

        assert "error" in admin_logs_handler("myagent")

    def test_no_email_rather_than_an_error(self, tmp_path, monkeypatch):
        from connectonion.useful_tools.send_email import get_agent_email

        monkeypatch.chdir(tmp_path)

        assert get_agent_email() is None

    def test_no_commands_rather_than_an_error(self, tmp_path, monkeypatch):
        from connectonion.useful_tools.slash_command import SlashCommand

        monkeypatch.chdir(tmp_path)

        assert SlashCommand.load("mycmd") is None
