"""`GET /admin/logs` looks for a file the agent never writes.

The endpoint rebuilds the path from the agent's *display* name:

    agent_name = agent_metadata["name"]
    ...
    log_path = project_co_dir() / "logs" / f"{agent_name}.log"

and `agent_metadata["name"]` is host.yaml's name, deliberately — the comment
above it says why, and for the relay, the directory and `/info` it is right:

    host.yaml's name, when it has one. The Agent object's name is whatever
    the code that built it chose — the co-ai template hardcodes "oo" …

The log file is named by the Logger from the *Agent's* name. The two are not
the same string, and `co init` makes them differ by default: host.yaml gets the
directory name while the Agent is named in code.

Measured against a real hosted agent, `Agent("e2eagent")` in a project whose
host.yaml says `name: e2e3`, started from a subdirectory, over real HTTP with
the admin bearer token:

    ls .co/logs/                                  e2eagent.log     (457 bytes)
    GET /admin/logs                               {"error": "No logs found"}
    cp .co/logs/e2eagent.log .co/logs/e2e3.log
    GET /admin/logs                               "A REAL LOG LINE…"

Same shape as #579, #614 and #660: a lookup compared against a value the thing
that produces it never produces. Nothing surfaced it because the unit tests
passed a name and created a file with that name, so both sides of the mismatch
were the test's own string. Only a real agent writes its log under one name and
serves it under another.

The fix asks the logger where its log is instead of rebuilding the path, which
also covers `Logger(log=...)` — an operator who set an explicit log file was
equally unreachable, whatever the names.

The path is not published: it stays out of `agent_metadata`, which goes to
`/info` and the relay directory, because an operator's filesystem layout is not
part of an agent's public profile.
"""

from pathlib import Path

import pytest


@pytest.fixture
def project(tmp_path, monkeypatch):
    co = tmp_path / "project" / ".co"
    (co / "logs").mkdir(parents=True)
    (co / "host.yaml").write_text("name: the-project\n")
    (tmp_path / "project" / "sub").mkdir()
    monkeypatch.chdir(tmp_path / "project")
    return tmp_path / "project"


def _an_agent(name, **kwargs):
    from connectonion import Agent

    return Agent(name, tools=[], model="co/gemini-2.5-flash", **kwargs)


class TestTheNamesDiffer:
    """host.yaml says one thing, the Agent is called another — the default."""

    def test_the_log_is_served(self, project):
        from connectonion.network.host.server import _create_route_handlers
        from connectonion.network.trust.trust_agent import TrustAgent

        agent = _an_agent("the-agent")
        agent.logger.log_file_path.write_text("A REAL LOG LINE\n")

        handlers = _create_route_handlers(
            lambda: agent, {"name": "the-project"}, 3600, TrustAgent("careful"), {})

        assert "A REAL LOG LINE" in handlers["admin_logs"]().get("content", "")

    def test_the_public_name_is_untouched(self, project):
        """The display name stays host.yaml's — that decision is not being undone."""
        from connectonion.network.host.server import _extract_agent_metadata

        metadata, _ = _extract_agent_metadata(lambda: _an_agent("the-agent"),
                                              "the-project")

        assert metadata["name"] == "the-project"

    def test_no_filesystem_path_is_published(self, project):
        """`/info` and the relay directory get this dict; a path is not public."""
        from connectonion.network.host.server import _extract_agent_metadata

        metadata, _ = _extract_agent_metadata(lambda: _an_agent("the-agent"),
                                              "the-project")

        assert not any("logs" in str(v) for v in metadata.values())


class TestAnExplicitLogFile:
    """`Logger(log=...)` was unreachable whatever the names matched."""

    def test_it_is_served(self, project, tmp_path):
        from connectonion.network.host.server import _create_route_handlers
        from connectonion.network.trust.trust_agent import TrustAgent

        elsewhere = tmp_path / "somewhere" / "custom.log"
        elsewhere.parent.mkdir()
        agent = _an_agent("the-agent", log=str(elsewhere))
        elsewhere.write_text("THE CUSTOM LOG\n")

        handlers = _create_route_handlers(
            lambda: agent, {"name": "the-project"}, 3600, TrustAgent("careful"), {})

        assert "THE CUSTOM LOG" in handlers["admin_logs"]().get("content", "")


class TestWhenTheNamesAgree:
    """This already worked and must keep working."""

    def test_the_log_is_still_served(self, project):
        from connectonion.network.host.server import _create_route_handlers
        from connectonion.network.trust.trust_agent import TrustAgent

        agent = _an_agent("the-project")
        agent.logger.log_file_path.write_text("MATCHING NAMES\n")

        handlers = _create_route_handlers(
            lambda: agent, {"name": "the-project"}, 3600, TrustAgent("careful"), {})

        assert "MATCHING NAMES" in handlers["admin_logs"]().get("content", "")


class TestWithNoLog:

    def test_it_reports_rather_than_raises(self, project):
        from connectonion.network.host.server import _create_route_handlers
        from connectonion.network.trust.trust_agent import TrustAgent

        agent = _an_agent("never-logged")
        if agent.logger.log_file_path.exists():
            agent.logger.log_file_path.unlink()

        handlers = _create_route_handlers(
            lambda: agent, {"name": "the-project"}, 3600, TrustAgent("careful"), {})

        assert "error" in handlers["admin_logs"]()


class TestTheHandlerItself:
    """`admin_logs_handler` takes the path now, not a name to rebuild one from."""

    def test_it_reads_the_file_it_is_given(self, tmp_path):
        from connectonion.network.host.http_router import admin_logs_handler

        log = tmp_path / "any.log"
        log.write_text("CONTENT\n")

        assert "CONTENT" in admin_logs_handler(log).get("content", "")

    def test_a_missing_file_is_reported(self, tmp_path):
        from connectonion.network.host.http_router import admin_logs_handler

        assert "error" in admin_logs_handler(tmp_path / "nothing.log")
