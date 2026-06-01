"""Tests for deploy command packaging helpers."""

import os
import subprocess
import tarfile
from pathlib import Path

import pytest

from connectonion.cli.commands import deploy_commands


def _run_git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)


def _init_repo(repo: Path) -> None:
    _run_git(repo, "init")
    _run_git(repo, "config", "user.email", "test@test.com")
    _run_git(repo, "config", "user.name", "Test")
    (repo / ".co").mkdir()
    (repo / ".co" / "host.yaml").write_text("name: demo\nentrypoint: agent.py\n", encoding="utf-8")
    (repo / "agent.py").write_text("print('project agent')\n", encoding="utf-8")
    _run_git(repo, "add", ".")
    _run_git(repo, "commit", "-m", "init")


def _write_skill(root: Path, name: str, body: str = "Body", requirements: str | None = None) -> Path:
    skill_dir = root / ".co" / "skills" / name
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: {name} skill\n---\n{body}\n",
        encoding="utf-8",
    )
    (skill_dir / "helper.txt").write_text("helper\n", encoding="utf-8")
    if requirements is not None:
        (skill_dir / "requirements.txt").write_text(requirements, encoding="utf-8")
    return skill_dir


def test_parse_skill_names_accepts_repeated_and_comma_separated_values():
    assert deploy_commands.parse_skill_names(["alpha,beta", " gamma "]) == ["alpha", "beta", "gamma"]


def test_resolve_deploy_skill_prefers_project_over_user_and_builtin(tmp_path, monkeypatch):
    project = tmp_path / "project"
    user_home = tmp_path / "home"
    project.mkdir()
    user_home.mkdir()
    project_skill = _write_skill(project, "alpha", "project")
    _write_skill(user_home, "alpha", "user")
    monkeypatch.setattr(Path, "home", lambda: user_home)

    assert deploy_commands.resolve_deploy_skill("alpha", project) == project_skill


def test_discover_deploy_skill_names_lists_project_then_user_with_project_priority(tmp_path, monkeypatch):
    project = tmp_path / "project"
    user_home = tmp_path / "home"
    project.mkdir()
    user_home.mkdir()
    _write_skill(project, "alpha", "project")
    _write_skill(project, "shared", "project")
    _write_skill(user_home, "beta", "user")
    _write_skill(user_home, "shared", "user")
    monkeypatch.setattr(Path, "home", lambda: user_home)

    assert deploy_commands.discover_deploy_skill_names(project) == ["alpha", "shared", "beta"]


def test_create_co_ai_deploy_package_with_all_skills_copies_project_and_user_skills(tmp_path, monkeypatch):
    project = tmp_path / "project"
    user_home = tmp_path / "home"
    project.mkdir()
    user_home.mkdir()
    _write_skill(project, "alpha", "project")
    _write_skill(project, "shared", "project")
    _write_skill(user_home, "beta", "user")
    _write_skill(user_home, "shared", "user")
    monkeypatch.setattr(Path, "home", lambda: user_home)

    package = deploy_commands.create_deploy_package(
        project_dir=project,
        template="co-ai",
        skills=[],
        all_skills=True,
        project_name="demo",
        entrypoint="agent.py",
        model="co/test-model",
        max_iterations=33,
    )

    with tarfile.open(package.tarball_path, "r:gz") as tar:
        names = set(tar.getnames())
        shared = tar.extractfile(".co/skills/shared/SKILL.md").read().decode("utf-8")

    assert ".co/skills/alpha/SKILL.md" in names
    assert ".co/skills/beta/SKILL.md" in names
    assert ".co/skills/shared/SKILL.md" in names
    assert "project" in shared
    assert "user" not in shared


def test_create_co_ai_deploy_package_is_self_contained_without_project_scaffold(tmp_path, monkeypatch):
    project = tmp_path / "project"
    project.mkdir()
    _write_skill(project, "alpha")
    before = sorted(str(p.relative_to(project)) for p in project.rglob("*"))
    monkeypatch.chdir(project)

    package = deploy_commands.create_deploy_package(
        project_dir=project,
        template="co-ai",
        skills=["alpha"],
        all_skills=False,
        project_name="demo",
        entrypoint="agent.py",
        model="co/test-model",
        max_iterations=33,
    )

    after = sorted(str(p.relative_to(project)) for p in project.rglob("*"))
    assert after == before
    assert package.entrypoint == ".co/deploy/co_ai_entrypoint.py"

    with tarfile.open(package.tarball_path, "r:gz") as tar:
        names = set(tar.getnames())
        assert ".co/deploy/co_ai_entrypoint.py" in names
        assert ".co/skills/alpha/SKILL.md" in names
        assert ".co/skills/alpha/helper.txt" in names
        assert "connectonion/cli/co_ai/agent.py" in names
        assert "pyproject.toml" in names
        assert "README.md" in names
        assert "requirements.txt" in names
        assert "Dockerfile" in names
        entrypoint = tar.extractfile(".co/deploy/co_ai_entrypoint.py").read().decode("utf-8")
        requirements = tar.extractfile("requirements.txt").read().decode("utf-8")
        dockerfile = tar.extractfile("Dockerfile").read().decode("utf-8")

    assert "create_coding_agent" in entrypoint
    assert "PACKAGE_ROOT = Path(__file__).resolve().parents[2]" in entrypoint
    assert "sys.path.insert(0, str(PACKAGE_ROOT))" in entrypoint
    assert "CO_DIR = PACKAGE_ROOT / \".co\"" in entrypoint
    assert entrypoint.index("sys.path.insert") < entrypoint.index("from connectonion import host")
    assert "model=\"co/test-model\"" in entrypoint
    assert "max_iterations=33" in entrypoint
    assert "name=\"demo\"" in entrypoint
    assert "auto_approve=True" not in entrypoint
    assert "browser_headless=True" in entrypoint
    assert "browser_channel=\"chrome\"" in entrypoint
    assert "co_dir=CO_DIR" in entrypoint
    assert "host(create_agent, trust=\"careful\", co_dir=CO_DIR)" in entrypoint
    assert requirements == ".\n"
    assert "FROM python:3.11-slim" in dockerfile
    assert "COPY pyproject.toml README.md requirements.txt ./" in dockerfile
    assert "COPY connectonion ./connectonion" in dockerfile
    assert "COPY .co ./.co" in dockerfile
    assert "COPY . ." not in dockerfile
    assert "RUN pip install --no-cache-dir -r requirements.txt" in dockerfile
    assert "python -m playwright install --with-deps chrome" in dockerfile
    assert "CMD [\"python\", \".co/deploy/co_ai_entrypoint.py\"]" in dockerfile


def test_create_co_ai_deploy_package_installs_skill_requirements(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    _write_skill(project, "image-gen", requirements="google-genai>=1.0\nPillow>=10\n")

    package = deploy_commands.create_deploy_package(
        project_dir=project,
        template="co-ai",
        skills=["image-gen"],
        all_skills=False,
        project_name="demo",
        entrypoint="agent.py",
        model="co/test-model",
        max_iterations=33,
    )

    with tarfile.open(package.tarball_path, "r:gz") as tar:
        names = set(tar.getnames())
        requirements = tar.extractfile("requirements.txt").read().decode("utf-8")
        skill_requirements = tar.extractfile(".co/skills/image-gen/requirements.txt").read().decode("utf-8")

    assert ".co/skills/image-gen/requirements.txt" in names
    assert requirements == ".\n-r .co/skills/image-gen/requirements.txt\n"
    assert "google-genai>=1.0" in skill_requirements


def test_create_co_ai_deploy_package_fails_before_upload_when_skill_missing(tmp_path):
    project = tmp_path / "project"
    project.mkdir()

    with pytest.raises(deploy_commands.DeployConfigError, match="Skill not found: missing"):
        deploy_commands.create_deploy_package(
            project_dir=project,
            template="co-ai",
            skills=["missing"],
            all_skills=False,
            project_name="demo",
            entrypoint="agent.py",
            model="co/test-model",
            max_iterations=33,
        )


@pytest.mark.parametrize("name", ["agent-4-linkedin", "co-ai", "a1"])
def test_validate_deploy_name_accepts_url_safe_names(name):
    assert deploy_commands.validate_deploy_name(name) == name


@pytest.mark.parametrize("name", ["Agent 4", "agent_4", "-agent", "agent-", ""])
def test_validate_deploy_name_rejects_names_that_break_agent_urls(name):
    with pytest.raises(deploy_commands.DeployConfigError):
        deploy_commands.validate_deploy_name(name)


def test_load_deploy_env_vars_merges_project_global_and_allowed_shell_keys(tmp_path, monkeypatch):
    project = tmp_path / "project"
    home = tmp_path / "home"
    project.mkdir()
    (home / ".co").mkdir(parents=True)
    (home / ".co" / "keys.env").write_text(
        "OPENONION_API_KEY=global-openonion\n"
        "GEMINI_API_KEY=global-gemini\n"
        "RANDOM_SECRET=do-not-upload\n",
        encoding="utf-8",
    )
    env_file = project / ".env"
    env_file.write_text(
        "GEMINI_API_KEY=project-gemini\n"
        "PROJECT_SETTING=enabled\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(Path, "home", lambda: home)
    for key in deploy_commands.DEPLOY_ENV_KEY_ALLOWLIST:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("GOOGLE_API_KEY", "shell-google")
    monkeypatch.setenv("RANDOM_SECRET", "shell-secret")

    env_vars = deploy_commands.load_deploy_env_vars(env_file)

    assert env_vars["OPENONION_API_KEY"] == "global-openonion"
    assert env_vars["GEMINI_API_KEY"] == "project-gemini"
    assert env_vars["GOOGLE_API_KEY"] == "shell-google"
    assert env_vars["PROJECT_SETTING"] == "enabled"
    assert "RANDOM_SECRET" not in env_vars
