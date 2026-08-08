"""One local skill preflight shared by doctor, installation, and startup."""

import importlib.metadata
import socket

from connectonion.skill_preflight import format_preflight_report, preflight_skills
from connectonion.skill_requirements import parse_skill_requirements


def _requirements(required=None, optional=None):
    return parse_skill_requirements({"requirements": {
        "version": 1,
        "required": required or {},
        "optional": optional or {},
    }}, "reporter")


def _run(requirements, **kwargs):
    defaults = {
        "environ": {},
        "which": lambda name: None,
        "package_version": lambda name: (_ for _ in ()).throw(
            importlib.metadata.PackageNotFoundError(name)
        ),
        "executable_version": lambda path: None,
    }
    defaults.update(kwargs)
    return preflight_skills([("reporter", requirements)], **defaults)


class TestLocalResolvers:
    def test_validation_has_no_network_side_effects(self, monkeypatch):
        def network_would_fail(*args, **kwargs):
            raise AssertionError("preflight attempted a network connection")

        monkeypatch.setattr(socket, "create_connection", network_would_fail)
        report = _run(_requirements(required={
            "python": [{"name": "local-package"}],
            "executables": [{"name": "local-command"}],
            "environment": [{"name": "LOCAL_VALUE"}],
            "oauth": [{"provider": "local-provider"}],
            "capabilities": [{"name": "local-capability"}],
        }))

        assert len(report.missing_required) == 5

    def test_python_package_version_matches(self):
        report = _run(
            _requirements(required={"python": [{"name": "pandas", "version": ">=2,<3"}]}),
            package_version=lambda name: "2.2.1",
        )

        assert report.ready
        assert report.checks[0].available

    def test_wrong_python_version_is_actionable(self):
        report = _run(
            _requirements(required={"python": [{
                "name": "pandas", "version": ">=2", "setup": "pip install -U pandas"
            }]}),
            package_version=lambda name: "1.5.0",
        )

        assert not report.ready
        assert "does not satisfy >=2" in format_preflight_report(report)
        assert "Setup: pip install -U pandas" in format_preflight_report(report)

    def test_executable_presence_and_version_are_checked(self):
        report = _run(
            _requirements(required={"executables": [{"name": "ffmpeg", "version": ">=6"}]}),
            which=lambda name: "/usr/bin/ffmpeg",
            executable_version=lambda path: "6.1",
        )

        assert report.ready

    def test_environment_variables_are_not_read_by_value(self):
        report = _run(
            _requirements(required={"environment": [{"name": "SECRET_TOKEN"}]}),
            environ={"SECRET_TOKEN": "do-not-print"},
        )

        assert report.ready
        assert "do-not-print" not in format_preflight_report(report)

    def test_oauth_requires_a_connection_and_scopes(self):
        report = _run(
            _requirements(required={"oauth": [{
                "provider": "google", "scopes": ["gmail.send", "drive.readonly"]
            }]}),
            environ={
                "GOOGLE_REFRESH_TOKEN": "secret",
                "GOOGLE_SCOPES": "https://www.googleapis.com/auth/gmail.send",
            },
        )

        assert not report.ready
        assert report.missing_required[0].detail == "missing OAuth scopes: drive.readonly"
        assert "secret" not in format_preflight_report(report)

    def test_capabilities_are_resolved_from_the_runtime_stamp(self):
        report = _run(
            _requirements(required={"capabilities": [{"name": "browser", "version": ">=2"}]}),
            environ={
                "CONNECTONION_CAPABILITIES": "browser,filesystem",
                "CONNECTONION_CAPABILITY_VERSIONS": "browser=2.1",
            },
        )

        assert report.ready


class TestRequiredAndOptional:
    def test_optional_findings_do_not_make_the_skill_unready(self):
        report = _run(_requirements(optional={"python": [{"name": "pyarrow"}]}))

        assert report.ready
        assert not report.missing_required
        assert len(report.missing_optional) == 1
        assert "[optional/python]" in format_preflight_report(report)

    def test_all_findings_are_one_report(self):
        report = _run(_requirements(
            required={"environment": [{"name": "MAIL_FROM"}]},
            optional={"executables": [{"name": "wkhtmltopdf"}]},
        ))

        rendered = format_preflight_report(report)
        assert rendered.count("Skill runtime preflight:") == 1
        assert "[required/environment]" in rendered
        assert "[optional/executables]" in rendered

    def test_a_skill_without_a_manifest_has_no_checks(self):
        report = _run(None)

        assert report.ready
        assert report.checks == ()
        assert format_preflight_report(report) == ""


class TestSharedEntryPoints:
    SKILL = (
        "---\nname: reporter\ndescription: Report\nrequirements:\n  version: 1\n"
        "  required:\n    environment:\n      - name: REPORT_TOKEN\n"
        "        setup: Set REPORT_TOKEN in .env\n---\n\nRun.\n"
    )

    def test_co_ai_startup_includes_one_preflight_report(self, tmp_path, monkeypatch, capsys):
        from connectonion.cli.co_ai.context import load_project_context
        from connectonion.cli.co_ai.skills import loader

        skill_dir = tmp_path / ".co" / "skills" / "reporter"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(self.SKILL)
        loader.SKILLS_REGISTRY.clear()
        monkeypatch.delenv("REPORT_TOKEN", raising=False)

        context = load_project_context(tmp_path)

        assert context.count("Skill runtime preflight:") == 1
        assert "REPORT_TOKEN" in capsys.readouterr().out

    def test_skill_copy_runs_the_same_preflight(self, tmp_path, monkeypatch, capsys):
        from connectonion.cli.commands import skills_commands

        source = tmp_path / "source" / "reporter"
        source.mkdir(parents=True)
        (source / "SKILL.md").write_text(self.SKILL)
        monkeypatch.delenv("REPORT_TOKEN", raising=False)

        copied = skills_commands._copy_entry(
            {"name": "reporter", "source": "test", "path": str(source / "SKILL.md")},
            force=False,
            skills_dir=tmp_path / "installed",
        )

        assert copied
        assert "Skill runtime preflight:" in capsys.readouterr().out

    def test_invalid_manifest_is_rejected_before_copy(self, tmp_path):
        from connectonion.cli.commands import skills_commands
        from connectonion.skill_requirements import SkillManifestError

        source = tmp_path / "source" / "broken"
        source.mkdir(parents=True)
        (source / "SKILL.md").write_text(
            self.SKILL.replace("version: 1", "version: next")
        )
        destination = tmp_path / "installed"

        import pytest
        with pytest.raises(SkillManifestError):
            skills_commands._copy_entry(
                {"name": "broken", "source": "test", "path": str(source / "SKILL.md")},
                force=False,
                skills_dir=destination,
            )

        assert not destination.exists()

    def test_required_missing_stops_the_co_ai_skill_before_instructions(self, tmp_path, monkeypatch):
        from connectonion.cli.co_ai.skills import loader
        from connectonion.cli.co_ai.skills.tool import skill

        skill_dir = tmp_path / ".co" / "skills" / "reporter"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(self.SKILL)
        loader.SKILLS_REGISTRY.clear()
        loader.load_skills(tmp_path)
        monkeypatch.delenv("REPORT_TOKEN", raising=False)

        result = skill("reporter")

        assert "Skill did not start." in result
        assert "Run." not in result

    def test_doctor_uses_the_shared_result_without_failing_optional(self, monkeypatch):
        from connectonion.cli.commands import doctor_commands
        from connectonion.useful_plugins.skills import SkillInfo

        rows = []

        class Table:
            def add_row(self, *values):
                rows.append(values)

        required = _requirements(required={"environment": [{"name": "MUST_HAVE"}]})
        optional = _requirements(optional={"environment": [{"name": "NICE_TO_HAVE"}]})
        skills = [
            SkillInfo("must", "", "project", requirements=required),
            SkillInfo("nice", "", "project", requirements=optional),
        ]
        monkeypatch.delenv("MUST_HAVE", raising=False)
        monkeypatch.delenv("NICE_TO_HAVE", raising=False)
        found = []

        doctor_commands._add_skill_preflight_rows(Table(), found, skills)

        assert any("MUST_HAVE" in problem for problem in found)
        assert not any("NICE_TO_HAVE" in problem for problem in found)
        assert any("optional" in status for _, status in rows)
