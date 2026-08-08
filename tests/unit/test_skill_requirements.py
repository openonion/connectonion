"""The versioned SKILL.md runtime requirements contract."""

import pytest

from connectonion.skill_requirements import (
    SkillManifestError,
    parse_skill_requirements,
)


def _manifest(**overrides):
    requirements = {"version": 1, "required": {}, "optional": {}}
    requirements.update(overrides)
    return {"requirements": requirements}


class TestCompatibility:
    def test_a_skill_without_requirements_still_loads(self):
        assert parse_skill_requirements({"name": "old-skill"}, "old-skill") is None

    def test_empty_sections_are_valid(self):
        parsed = parse_skill_requirements(_manifest(), "simple")

        assert parsed.version == 1
        assert parsed.required == ()
        assert parsed.optional == ()


class TestSchema:
    def test_every_requirement_kind_is_normalized(self):
        frontmatter = _manifest(required={
            "python": [{"name": "httpx", "version": ">=0.27,<1", "setup": "pip install httpx"}],
            "executables": [{"name": "ffmpeg", "version": ">=6"}],
            "environment": [{"name": "OPENAI_API_KEY", "setup": "Set it in .env"}],
            "oauth": [{"provider": "google", "scopes": ["gmail.send", "drive.readonly"]}],
            "capabilities": [{"name": "browser", "version": ">=1"}],
        })

        parsed = parse_skill_requirements(frontmatter, "media-mail")

        assert [item.category for item in parsed.required] == [
            "python", "executables", "environment", "oauth", "capabilities"
        ]
        assert parsed.required[0].name == "httpx"
        assert parsed.required[0].version == ">=0.27,<1"
        assert parsed.required[0].setup == "pip install httpx"
        assert parsed.required[3].name == "google"
        assert parsed.required[3].scopes == ("gmail.send", "drive.readonly")

    def test_required_and_optional_stay_separate(self):
        parsed = parse_skill_requirements(_manifest(
            required={"python": [{"name": "core"}]},
            optional={"python": [{"name": "faster"}]},
        ), "split")

        assert [item.name for item in parsed.required] == ["core"]
        assert [item.name for item in parsed.optional] == ["faster"]


class TestPreciseFailures:
    @pytest.mark.parametrize(
        ("frontmatter", "field"),
        [
            ({"requirements": []}, "requirements"),
            ({"requirements": {}}, "requirements.version"),
            (_manifest(version="1"), "requirements.version"),
            (_manifest(version=2), "requirements.version"),
            (_manifest(required=[]), "requirements.required"),
            (_manifest(required={"python": {}}), "requirements.required.python"),
            (_manifest(required={"python": [{}]}), "requirements.required.python[0].name"),
            (_manifest(required={"python": [{"name": "--extra-index-url"}]}),
             "requirements.required.python[0].name"),
            (_manifest(required={"environment": [{"name": "NOT-AN-ENV-VAR"}]}),
             "requirements.required.environment[0].name"),
            (_manifest(required={"python": [{"name": "x", "version": ""}]}),
             "requirements.required.python[0].version"),
            (_manifest(required={"python": [{"name": "x", "version": "version two"}]}),
             "requirements.required.python[0].version"),
            (_manifest(required={"oauth": [{"provider": "google", "scopes": "gmail.send"}]}),
             "requirements.required.oauth[0].scopes"),
            (_manifest(required={"oauth": [{"provider": "google", "scopes": [""]}]}),
             "requirements.required.oauth[0].scopes[0]"),
            (_manifest(required={"python": [{"name": "x", "scopes": []}]}),
             "requirements.required.python[0].scopes"),
            (_manifest(required={"containers": []}), "requirements.required.containers"),
            ({"requirements": {"version": 1, "future": {}}}, "requirements.future"),
        ],
    )
    def test_error_names_the_skill_and_exact_field(self, frontmatter, field):
        with pytest.raises(SkillManifestError) as caught:
            parse_skill_requirements(frontmatter, "send-report")

        assert caught.value.skill_name == "send-report"
        assert caught.value.field == field
        assert "Skill 'send-report'" in str(caught.value)
        assert field in str(caught.value)


class TestLoaderIntegration:
    def test_plugin_loader_returns_the_validated_contract(self, tmp_path, monkeypatch):
        import importlib

        skills = importlib.import_module("connectonion.useful_plugins.skills")

        skill_dir = tmp_path / ".co" / "skills" / "mailer"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(
            "---\nname: mailer\ndescription: Mail\nrequirements:\n  version: 1\n"
            "  required:\n    environment:\n      - name: MAIL_FROM\n---\n\nSend it.\n"
        )
        monkeypatch.setattr(skills, "_get_skill_paths", lambda name: [skill_dir / "SKILL.md"])

        loaded = skills._load_skill("mailer")

        assert loaded["requirements"].required[0].name == "MAIL_FROM"

    def test_co_ai_loader_keeps_the_same_contract(self, tmp_path):
        from connectonion.cli.co_ai.skills.loader import _parse_skill_file

        skill_dir = tmp_path / "mailer"
        skill_dir.mkdir()
        path = skill_dir / "SKILL.md"
        path.write_text(
            "---\nname: mailer\ndescription: Mail\nrequirements:\n  version: 1\n"
            "  optional:\n    capabilities:\n      - name: browser\n---\n\nSend it.\n"
        )

        info = _parse_skill_file(path)

        assert info.requirements.optional[0].name == "browser"

    def test_doctor_reports_an_invalid_manifest(self, tmp_path):
        from connectonion.useful_plugins.skills import find_skill_problems

        skill_dir = tmp_path / ".co" / "skills" / "mailer"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(
            "---\nname: mailer\ndescription: Mail\nrequirements:\n  version: 1\n"
            "  required:\n    python:\n      - name: httpx\n        version: 3\n---\n\nSend it.\n"
        )

        problems = find_skill_problems(co_dir=tmp_path / ".co")

        assert len(problems) == 1
        assert "Skill 'mailer'" in problems[0][2]
        assert "requirements.required.python[0].version" in problems[0][2]
