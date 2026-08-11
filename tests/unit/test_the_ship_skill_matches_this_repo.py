"""The shipped release skill tells you to edit a file this repo does not have.

`ship-feature/SKILL.md` is a procedure an agent follows to cut a release. It ships
inside the package, in two copies, and both say:

    2. `setup.py` — `version="X.Y.Z"`
    git add connectonion/__init__.py setup.py tests/ docs/
    python setup.py sdist bdist_wheel
    - [ ] Version bumped in `__init__.py` and `setup.py`

There is no setup.py in this repository. The version lives in two places:

    pyproject.toml     version = "1.5.11"
    connectonion/_version.py   __version__ = "1.5.11"

and the build backend is hatchling, so `python setup.py sdist bdist_wheel` is not
a command that exists here — it is the setuptools invocation from a different
project layout.

An agent following this skill bumps a file it has to create, stages a path that
is not there, and runs a build that fails. Worse than a wrong doc: this one is
executed.

The same failure family as #717, #724, #726 — instructions trusted while the code
moved — except the reader here is a program.
"""

import pathlib

import pytest


ROOT = pathlib.Path(__file__).resolve().parents[2]
SKILLS = [ROOT / "connectonion/useful_skills/ship-feature/SKILL.md"]


@pytest.fixture(params=SKILLS, ids=lambda p: p.parent.parent.name)
def skill(request):
    if not request.param.is_file():
        pytest.skip(f"{request.param} not shipped")
    return request.param.read_text(encoding="utf-8")


class TestItDoesNotSendYouToSetupPy:

    def test_setup_py_is_absent_from_the_repo(self):
        """The premise. If someone adds one, this test should be revisited."""
        assert not (ROOT / "setup.py").exists()

    def test_it_does_not_tell_you_to_edit_it(self, skill):
        """Naming setup.py as one place a version *might* live is fine — the
        useful_skills copy searches before editing and is written to work in any
        repo. Instructing an edit to it, in a repo that has none, is not."""
        for instruction in ('`setup.py` — `version=',
                            "git add connectonion/__init__.py setup.py",
                            "Version bumped in `__init__.py` and `setup.py`"):
            assert instruction not in skill, instruction

    def test_it_does_not_tell_you_to_build_with_it(self, skill):
        assert "python setup.py" not in skill


class TestItNamesWhereTheVersionActuallyIs:

    def test_pyproject_is_mentioned(self, skill):
        assert "pyproject.toml" in skill

    def test_the_version_module_is_mentioned(self, skill):
        assert "_version.py" in skill

    def test_both_places_really_hold_a_version(self):
        """The claim the skill will be making."""
        import re

        pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
        version_py = (ROOT / "connectonion/_version.py").read_text(encoding="utf-8")

        # PEP 440 versions may include a pre-release segment (for example,
        # ``1.7.0a1``), so compare the complete quoted values rather than only
        # digits and dots.
        in_pyproject = re.search(r'^version = "([^"]+)"', pyproject, re.M)
        in_module = re.search(r'__version__ = "([^"]+)"', version_py)

        assert in_pyproject and in_module
        assert in_pyproject.group(1) == in_module.group(1), (
            "the two version strings disagree, which is what a release skill "
            "naming both of them is for"
        )


class TestTheBuildCommandIsTheRealOne:

    def test_the_backend_is_hatchling(self):
        pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")

        assert "hatchling" in pyproject

    def test_the_skill_uses_a_pep517_build(self, skill):
        assert "python -m build" in skill or "hatch build" in skill


class TestReleaseIsAContributorSkill:
    """The release procedure remains copyable but is not a customer default."""

    def test_a_clean_home_does_not_load_it(self, tmp_path, monkeypatch):
        from connectonion.useful_plugins.skills import _load_skill

        monkeypatch.setattr(pathlib.Path, "home", classmethod(lambda cls: tmp_path))
        monkeypatch.chdir(tmp_path)

        loaded = _load_skill("ship-feature")

        assert loaded is None

    def test_library_copy_names_the_real_version_files(self):
        body = (ROOT / "connectonion/useful_skills/ship-feature/SKILL.md").read_text()

        assert "_version.py" in body
        assert "pyproject.toml" in body

    def test_library_copy_does_not_instruct_a_setup_py_build(self):
        body = (ROOT / "connectonion/useful_skills/ship-feature/SKILL.md").read_text()

        assert "python setup.py" not in body
        assert "python -m build" in body


class TestTheSkillIsStillAReleaseProcedure:
    """Guard against fixing this by gutting the file."""

    def test_it_still_covers_the_steps(self, skill):
        lowered = skill.lower()

        for step in ("version", "test", "git", "pypi"):
            assert step in lowered

    def test_it_is_not_empty(self, skill):
        assert len(skill.splitlines()) > 20


class TestTheDesignJournalIsPartOfShipping:
    """A public design record is part of a meaningful release, not cleanup."""

    def test_the_skill_names_the_design_journal_surfaces(self, skill):
        for required in ("Design Journal", "canonical URL", "sitemaps", "llms.txt"):
            assert required in skill

    def test_the_skill_does_not_publish_availability_before_artifacts(self, skill):
        assert "After the exact PyPI package and GitHub Release are public" in skill
