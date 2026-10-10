"""The command index `co init` writes into Codex's and Claude Code's always-loaded files.

Codex and Claude Code had no way to learn that `co` exists: asked to "hand
this task to Ody", Codex went nowhere, and `co ai` with no rule opened a
browser in 3 of 3 runs instead of using `co linear` (#2113). The fix is a
generated block between markers in ~/.codex/AGENTS.md and ~/.claude/CLAUDE.md.

Every test runs in the tmp HOME conftest gives it; none may reach the real
~/.codex or ~/.claude.
"""

import stat
from pathlib import Path

import pytest
import typer
from typer.testing import CliRunner

from connectonion import __version__
from connectonion.cli.commands import agent_index
from connectonion.cli.main import app

USER_TEXT = "# My rules\n\nAlways answer in English.\n"


@pytest.fixture
def tools():
    """Both tools installed: their directories exist, their files do not."""
    codex, claude = Path.home() / ".codex", Path.home() / ".claude"
    codex.mkdir()
    claude.mkdir()
    return codex / "AGENTS.md", claude / "CLAUDE.md"


def test_the_tests_never_see_the_real_home():
    assert "pytest-of-" in str(Path.home())


class TestGenerated:

    def test_every_visible_top_level_command_is_listed(self):
        body = agent_index.generate(app)
        import typer.main
        root = typer.main.get_command(app)
        for name, cmd in root.commands.items():
            if cmd.hidden:
                assert f"co {name} —" not in body
            else:
                assert f"\nco {name} — " in body, name

    def test_a_new_group_shows_up_and_hidden_deprecated_do_not(self):
        fake = typer.Typer()
        zebra = typer.Typer(help="Zebra crossings: list and paint them.")
        zebra.command("ls")(lambda: None)
        fake.add_typer(zebra, name="zebra")
        trial = typer.Typer(help="Experimental: trial balloons. Targets 2.0.")
        trial.command("go")(lambda: None)
        fake.add_typer(trial, name="trial")
        ghost = typer.Typer(help="Ghost.")
        ghost.command("boo")(lambda: None)
        fake.add_typer(ghost, name="ghost", hidden=True)
        fake.command("old", deprecated=True)(lambda: None)

        body = agent_index.generate(fake)

        assert "co zebra — Zebra crossings: list and paint them." in body
        assert "co trial — Experimental: trial balloons." in body
        assert "ghost" not in body
        assert "co old" not in body
        assert "co zebra ls" not in body          # subcommands stay in --help

    def test_rules_come_first_and_name_the_discovery_commands(self):
        body = agent_index.generate(app)
        rules = body.split("\n\n")[0]
        assert "co commands" in rules and "co <cmd> --help" in rules
        assert "credentials" in rules

    def test_size_stays_small(self):
        block = agent_index.block(agent_index.generate(app))
        assert len(block.splitlines()) <= 65
        assert len(block) <= 12_000          # ~3k tokens at 4 chars a token


class TestWrite:

    def test_writes_both_files_with_the_version(self, tools):
        changed = agent_index.refresh(app)
        assert [path for path, _, _ in changed] == list(tools)
        for path in tools:
            text = path.read_text(encoding="utf-8")
            assert text.startswith(f"<!-- co:begin {__version__} -->\n")
            assert text.rstrip().endswith("<!-- co:end -->")
            assert agent_index.stamp(path) == __version__

    def test_rerun_is_idempotent_and_writes_nothing(self, tools):
        agent_index.refresh(app)
        before = [p.read_bytes() for p in tools]
        for path in tools:
            path.chmod(stat.S_IRUSR)               # a write would now raise
        assert agent_index.refresh(app) == []
        assert [p.read_bytes() for p in tools] == before

    def test_text_outside_the_markers_stays_byte_identical(self, tools):
        codex = tools[0]
        codex.write_text(USER_TEXT, encoding="utf-8")
        agent_index.refresh(app)
        assert codex.read_text(encoding="utf-8").startswith(USER_TEXT)

        # The user adds text after the block; a refresh after an upgrade
        # rewrites only the block.
        tail = "\n## Later notes\nkeep me\n"
        codex.write_text(codex.read_text(encoding="utf-8") + tail, encoding="utf-8")
        old = codex.read_text(encoding="utf-8").replace(f"co:begin {__version__}", "co:begin 0.0.1")
        codex.write_text(old, encoding="utf-8")
        head, _, rest = old.partition("<!-- co:begin")
        after = rest.partition("<!-- co:end -->")[2]

        agent_index.refresh(app)
        new = codex.read_text(encoding="utf-8")
        assert new.startswith(head) and new.endswith(after)
        assert agent_index.stamp(codex) == __version__

    def test_remove_restores_the_file_exactly(self, tools):
        codex, claude = tools
        codex.write_text(USER_TEXT, encoding="utf-8")
        agent_index.refresh(app)
        removed = agent_index.remove()
        assert removed == [codex, claude]
        assert codex.read_text(encoding="utf-8") == USER_TEXT
        assert not claude.exists()                 # we created it, so it goes

    def test_a_missing_tool_directory_is_never_created(self):
        (Path.home() / ".claude").mkdir()
        changed = agent_index.refresh(app)
        assert [p for p, _, _ in changed] == [Path.home() / ".claude" / "CLAUDE.md"]
        assert not (Path.home() / ".codex").exists()

    def test_no_tool_directories_means_no_work(self):
        """A server with no human (co deploy --to, Docker, CI) has neither."""
        assert agent_index.refresh(app) == []
        assert agent_index.stale() == []
        assert not (Path.home() / ".codex").exists()
        assert not (Path.home() / ".claude").exists()


class TestCli:

    def test_skills_index_writes_and_prints_paths_and_how_to_remove(self, tools):
        result = CliRunner().invoke(app, ["skills", "index"])
        assert result.exit_code == 0, result.output
        for path in tools:
            assert str(path) in result.output
        assert "co skills index --remove" in result.output
        assert "Next:" in result.output

    def test_skills_index_remove(self, tools):
        CliRunner().invoke(app, ["skills", "index"])
        result = CliRunner().invoke(app, ["skills", "index", "--remove"])
        assert result.exit_code == 0, result.output
        assert not tools[0].exists() and not tools[1].exists()

    def test_global_init_writes_the_block_and_links_skills(self, tools, monkeypatch):
        from connectonion.cli.commands import init
        monkeypatch.setattr(init, "authenticate", lambda *a, **k: True)
        init.handle_global_init()
        for path in tools:
            assert agent_index.stamp(path) == __version__
        assert (Path.home() / ".codex" / "skills" / "co-linear" / "SKILL.md").exists()


class TestDoctor:

    def test_doctor_reports_missing_then_stale(self, tools):
        assert agent_index.stale() == [(tools[0], None), (tools[1], None)]
        agent_index.refresh(app)
        assert agent_index.stale() == []
        text = tools[1].read_text(encoding="utf-8").replace(__version__, "0.0.1", 1)
        tools[1].write_text(text, encoding="utf-8")
        assert agent_index.stale() == [(tools[1], "0.0.1")]

    def test_doctor_row_names_the_stale_version_and_the_next_command(self, tools):
        agent_index.refresh(app)
        text = tools[1].read_text(encoding="utf-8").replace(__version__, "0.0.1", 1)
        tools[1].write_text(text, encoding="utf-8")
        rows = agent_index.doctor_rows()
        claude_row = [r for r in rows if "CLAUDE.md" in r[1]][0]
        assert "stale" in claude_row[1] and "0.0.1" in claude_row[1]
        assert "co skills index" in claude_row[1]
        assert claude_row[0] == "warning"


class TestHostStartup:
    """host() refreshes the block: after `pip install -U` nobody re-runs co init."""

    def _host_until_port_check(self, tmp_path, monkeypatch):
        """Run the real host() up to its port check, then stop it there."""
        from connectonion import Agent
        from connectonion.network.host import server
        monkeypatch.setattr(server, "_port_in_use", lambda port: True)
        co_dir = tmp_path / "proj" / ".co"
        co_dir.mkdir(parents=True)
        agent = Agent("t", model="co/gemini-2.5-flash", quiet=True)
        with pytest.raises(SystemExit):
            server.host(agent, port=18999, co_dir=co_dir, relay_url=None)

    def test_refreshes_a_stale_block(self, tools, tmp_path, capsys, monkeypatch):
        agent_index.refresh(app)
        tools[0].write_text(tools[0].read_text(encoding="utf-8").replace(__version__, "0.0.1", 1),
                            encoding="utf-8")
        capsys.readouterr()
        self._host_until_port_check(tmp_path, monkeypatch)
        assert agent_index.stamp(tools[0]) == __version__
        out = capsys.readouterr().out
        assert str(tools[0]) in out and f"0.0.1 → {__version__}" in out

    def test_leaves_a_current_block_alone_and_prints_nothing(self, tools, tmp_path, capsys, monkeypatch):
        agent_index.refresh(app)
        for path in tools:
            path.chmod(stat.S_IRUSR)
        capsys.readouterr()
        self._host_until_port_check(tmp_path, monkeypatch)
        assert "AGENTS.md" not in capsys.readouterr().out

    def test_skips_missing_tool_directories(self, tmp_path, monkeypatch):
        self._host_until_port_check(tmp_path, monkeypatch)
        assert not (Path.home() / ".codex").exists()
        assert not (Path.home() / ".claude").exists()


def test_co_doctor_prints_the_stale_row(tools, capsys):
    agent_index.refresh(app)
    tools[0].write_text(tools[0].read_text(encoding="utf-8").replace(__version__, "0.0.1", 1),
                        encoding="utf-8")
    from connectonion.cli.commands.doctor_commands import handle_doctor
    handle_doctor()
    out = " ".join(capsys.readouterr().out.split())
    assert "Command index" in out
    assert "0.0.1" in out and "co skills index" in out
