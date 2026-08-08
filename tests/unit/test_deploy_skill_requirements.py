"""Declared skill dependencies travel and converge before service restart."""

import json
import tarfile
from unittest.mock import patch

from connectonion.cli.commands import deploy_commands, deploy_to_server
from connectonion.skill_deploy import collect_deploy_skill_requirements

SKILL = """---
name: reporter
description: Build a report
requirements:
  version: 1
  required:
    python:
      - name: pandas
        version: ">=2.2,<3"
---

Build it.
"""


def _project(tmp_path, skill=SKILL):
    project = tmp_path / "project"
    skill_dir = project / ".co" / "skills" / "reporter"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(skill)
    (skill_dir / "template.txt").write_text("asset")
    (project / "agent.py").write_text("print('ok')")
    return project


def _ok(stdout=""):
    class Result:
        returncode = 0
        stderr = ""
    result = Result()
    result.stdout = stdout
    return result


def _fail(stderr="failed"):
    class Result:
        returncode = 1
        stdout = ""
    result = Result()
    result.stderr = stderr
    return result


class TestCollectionAndPackaging:
    def test_python_constraints_are_canonical(self, tmp_path):
        requirements = collect_deploy_skill_requirements(_project(tmp_path))

        assert requirements.python == ("pandas>=2.2,<3",)
        assert requirements.skills == ("reporter",)
        assert len(requirements.digest) == 64

    def test_skill_manifest_assets_and_generated_contract_travel(self, tmp_path):
        project = _project(tmp_path)

        tarball = deploy_commands._build_tarball(project, [])

        with tarfile.open(tarball) as archive:
            names = archive.getnames()
            assert ".co/skills/reporter/SKILL.md" in names
            assert ".co/skills/reporter/template.txt" in names
            assert ".co/skill-python-requirements.txt" in names
            assert archive.extractfile(".co/skill-python-requirements.txt").read() == b"pandas>=2.2,<3\n"
            requested = json.load(archive.extractfile(".co/skill-requirements.requested.json"))
            assert requested["python"] == ["pandas>=2.2,<3"]
            assert requested["digest"]

    def test_external_skill_manifest_and_assets_travel_together(self, tmp_path):
        project = tmp_path / "project"
        project.mkdir()
        (project / "agent.py").write_text("print('ok')")
        external = tmp_path / "external"
        external.mkdir()
        (external / "SKILL.md").write_text(SKILL)
        (external / "template.txt").write_text("asset")

        tarball = deploy_commands._build_tarball(project, [external])

        with tarfile.open(tarball) as archive:
            assert ".co/skills/external/SKILL.md" in archive.getnames()
            assert ".co/skills/external/template.txt" in archive.getnames()
            assert archive.extractfile(".co/skill-python-requirements.txt").read() == b"pandas>=2.2,<3\n"


class TestServerRealization:
    def test_changed_manifest_installs_and_stamps_realized_state(self, tmp_path):
        project = _project(tmp_path)
        requirements = collect_deploy_skill_requirements(project)

        with patch.object(deploy_to_server, "_ssh", side_effect=[_ok("old"), _ok()]) as ssh:
            assert deploy_to_server._install_deps_if_changed(
                "user@host", "agent", project, requirements
            )

        command = ssh.call_args_list[-1].args[1]
        assert "pip install -q -U 'pandas>=2.2,<3'" in command
        assert "pip freeze --all" in command
        assert command.index("pip freeze --all") < command.index("requirements.sha256")

    def test_unchanged_manifest_skips_install(self, tmp_path):
        project = _project(tmp_path)
        requirements = collect_deploy_skill_requirements(project)
        import hashlib

        from connectonion import __version__

        digest = hashlib.sha256(
            b"\nskills:" + requirements.digest.encode()
            + b"\ncli:" + __version__.encode()
        ).hexdigest()

        with patch.object(deploy_to_server, "_ssh", return_value=_ok(digest)) as ssh:
            assert deploy_to_server._install_deps_if_changed(
                "user@host", "agent", project, requirements
            )

        assert ssh.call_count == 1

    def test_failed_install_is_retried_because_no_stamp_is_written(self, tmp_path):
        project = _project(tmp_path)
        requirements = collect_deploy_skill_requirements(project)

        with patch.object(
            deploy_to_server, "_ssh", side_effect=[_ok("old"), _fail(), _ok("old"), _ok()]
        ) as ssh:
            assert not deploy_to_server._install_deps_if_changed(
                "user@host", "agent", project, requirements
            )
            assert deploy_to_server._install_deps_if_changed(
                "user@host", "agent", project, requirements
            )

        installs = [call.args[1] for call in ssh.call_args_list if "pip install" in call.args[1]]
        assert len(installs) == 2


class TestUnsupportedRequirements:
    def test_required_binary_is_named_before_any_server_call(self, tmp_path, capsys):
        skill = SKILL.replace(
            "    python:\n      - name: pandas\n        version: \">=2.2,<3\"",
            "    executables:\n      - name: ffmpeg\n        setup: Install ffmpeg on the server",
        )
        project = _project(tmp_path, skill)
        (project / ".co" / "host.yaml").write_text("name: reporter\nentrypoint: agent.py\n")

        with patch.object(deploy_to_server.shutil, "which", return_value="/usr/bin/tool"), \
             patch.object(deploy_to_server, "load_server", return_value={"ssh": "user@host"}), \
             patch.object(deploy_to_server, "_ssh") as ssh:
            assert not deploy_to_server.handle_deploy_to("prod", project)

        ssh.assert_not_called()
        output = capsys.readouterr().out
        assert "ffmpeg" in output
        assert "Install ffmpeg on the server" in output
