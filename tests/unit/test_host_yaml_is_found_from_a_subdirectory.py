"""An agent started one directory down is still the agent host.yaml describes.

`load_host_config` resolved against the bare cwd:

    co_dir = Path.cwd() / '.co'

so starting the agent from a subdirectory found no `host.yaml` and every value
in it fell back to a default. Measured on a project whose file says
`trust: careful` and `port: 8806`, with 88 permission entries:

    from the project root       port 8806   trust careful   permissions 88
    from a subdirectory of it   port None   trust None      permissions 0

The three fall back in different directions:

    port          -> 8000, so the agent listens somewhere else than configured
    permissions   -> none auto-approved, so everything asks: safe
    trust         -> "careful", the default in server.py

The last one is the reason this is not merely untidy. A project that says
`trust: strict` — whitelist only, no onboarding — runs as `careful` instead,
which admits contacts and accepts an invite code. The configuration says one
thing and the running agent enforces something looser, with nothing said.

Same shape as #660, and the same rule applies: the directory that owns `.co/` is
the project, not wherever the process was started. dashboard.py settled it for
the Home page and wrote it down; #660 did the trust lists.
"""

from pathlib import Path

import pytest

from connectonion.network.host.config import load_host_config


@pytest.fixture
def project(tmp_path):
    co = tmp_path / "project" / ".co"
    co.mkdir(parents=True)
    (co / "host.yaml").write_text(
        "name: configured\n"
        "port: 8806\n"
        "trust: strict\n"
        "permissions:\n"
        "  read_file:\n"
        "    allowed: true\n"
    )
    (tmp_path / "project" / "subdir" / "deeper").mkdir(parents=True)
    return tmp_path / "project"


class TestFromASubdirectory:

    def test_the_configured_port_is_used(self, project, monkeypatch):
        monkeypatch.chdir(project / "subdir")

        assert load_host_config(None).get("port") == 8806

    def test_the_configured_trust_is_used(self, project, monkeypatch):
        """The direction that matters: strict must not become careful."""
        monkeypatch.chdir(project / "subdir")

        assert load_host_config(None).get("trust") == "strict"

    def test_the_permissions_come_with_it(self, project, monkeypatch):
        monkeypatch.chdir(project / "subdir")

        assert "read_file" in (load_host_config(None).get("permissions") or {})

    def test_two_levels_down_as_well(self, project, monkeypatch):
        monkeypatch.chdir(project / "subdir" / "deeper")

        assert load_host_config(None).get("name") == "configured"


class TestFromTheProjectRoot:
    """Unchanged — this already worked."""

    def test_it_still_reads_the_file(self, project, monkeypatch):
        monkeypatch.chdir(project)

        config = load_host_config(None)
        assert config.get("port") == 8806
        assert config.get("trust") == "strict"


class TestWhatMustNotChange:

    def test_an_explicit_co_dir_still_wins(self, project, tmp_path, monkeypatch):
        other = tmp_path / "other" / ".co"
        other.mkdir(parents=True)
        (other / "host.yaml").write_text("name: explicit\nport: 9999\n")
        monkeypatch.chdir(project)

        assert load_host_config(other).get("port") == 9999

    def test_code_parameters_still_override_the_file(self, project, monkeypatch):
        monkeypatch.chdir(project / "subdir")

        assert load_host_config(None, port=7777).get("port") == 7777

    def test_outside_any_project_there_is_simply_no_file(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)

        assert load_host_config(None).get("port") is None


class TestHostItselfUsesIt:
    """A resolver the real path does not reach is the bug, not the fix.

    `host()` computed `co_dir = Path.cwd() / '.co'` before calling
    load_host_config, so fixing only the loader would have changed nothing for
    an actual agent.
    """

    def test_the_configured_port_reaches_uvicorn(self, project, monkeypatch):
        from connectonion import Agent, address
        from connectonion.network.host import server as server_module

        address.save(address.generate(), project / ".co")
        monkeypatch.chdir(project / "subdir")

        seen = {}
        monkeypatch.setattr(server_module.uvicorn, "run", lambda app, **kw: seen.update(kw))
        monkeypatch.setattr(server_module, "_print_host_banner", lambda **kw: None)

        server_module.host(Agent("t", tools=[], model="co/gemini-2.5-flash"),
                           relay_url=None)

        assert seen.get("port") == 8806

    def test_the_configured_trust_is_what_it_serves(self, project, monkeypatch):
        from connectonion import Agent, address
        from connectonion.network.host import server as server_module

        address.save(address.generate(), project / ".co")
        monkeypatch.chdir(project / "subdir")

        seen = {}
        monkeypatch.setattr(server_module.uvicorn, "run", lambda app, **kw: None)
        monkeypatch.setattr(server_module, "_print_host_banner", lambda **kw: seen.update(kw))

        server_module.host(Agent("t", tools=[], model="co/gemini-2.5-flash"),
                           relay_url=None)

        assert seen.get("trust") == "strict", "the agent served a looser trust than configured"
