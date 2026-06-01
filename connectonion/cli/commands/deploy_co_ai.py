"""Build co-ai deploy packages and resolve deploy-time skills/env."""

import json
import os
import re
import shutil
import tarfile
import tempfile
from dataclasses import dataclass
from pathlib import Path

from dotenv import dotenv_values

from connectonion import __version__


CO_AI_ENTRYPOINT = ".co/deploy/co_ai_entrypoint.py"
PACKAGE_ROOT = Path(__file__).resolve().parents[2]
PROJECT_ROOT = PACKAGE_ROOT.parent
DEPLOY_NAME_PATTERN = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")
DEPLOY_ENV_KEY_ALLOWLIST = (
    "OPENONION_API_KEY",
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "GEMINI_API_KEY",
    "GOOGLE_API_KEY",
    "GROQ_API_KEY",
    "XAI_API_KEY",
    "OPENROUTER_API_KEY",
    "CONNECTONION_API_KEY",
)


class DeployConfigError(Exception):
    """Raised when deploy configuration is invalid before upload."""


@dataclass
class DeployPackage:
    tarball_path: Path
    entrypoint: str


def parse_skill_names(raw_skills: list[str] | None) -> list[str]:
    """Parse repeated/comma-separated --skills values."""
    if not raw_skills:
        return []

    names = []
    for value in raw_skills:
        for part in value.split(","):
            name = part.strip()
            if name:
                names.append(name)
    return names


def validate_deploy_name(name: str) -> str:
    """Validate a deploy name that becomes part of the hosted agent URL."""
    if not name or not DEPLOY_NAME_PATTERN.match(name):
        raise DeployConfigError(
            "Invalid deploy name. Use lowercase letters, numbers, and hyphens; "
            "start and end with a letter or number."
        )
    return name


def _filter_allowed_env(values: dict) -> dict:
    return {
        key: value
        for key, value in values.items()
        if key in DEPLOY_ENV_KEY_ALLOWLIST and value not in (None, "")
    }


def load_deploy_env_vars(env_file: str | Path) -> dict:
    """Load env vars for deploy without dumping the full shell environment."""
    env_vars = {}

    global_env = Path.home() / ".co" / "keys.env"
    if global_env.exists():
        env_vars.update(_filter_allowed_env(dotenv_values(global_env)))

    env_vars.update({
        key: value
        for key in DEPLOY_ENV_KEY_ALLOWLIST
        if (value := os.environ.get(key))
    })

    env_path = Path(env_file)
    if env_path.exists():
        env_vars.update({
            key: value
            for key, value in dotenv_values(env_path).items()
            if value is not None
        })

    return env_vars


def resolve_deploy_skill(name: str, project_dir: Path) -> Path:
    """Resolve a deploy skill directory by project > user > built-in priority."""
    candidates = [
        project_dir / ".co" / "skills" / name,
        Path.home() / ".co" / "skills" / name,
        Path(__file__).parent.parent / "co_ai" / "skills" / "builtin" / name,
    ]
    for skill_dir in candidates:
        if (skill_dir / "SKILL.md").exists():
            return skill_dir

    raise DeployConfigError(
        f"Skill not found: {name}. Run `co skills discover && co skills copy {name}` first."
    )


def discover_deploy_skill_names(project_dir: Path) -> list[str]:
    """Discover deployable project/user skill names with project priority."""
    names = []
    seen = set()
    for skills_dir in (project_dir / ".co" / "skills", Path.home() / ".co" / "skills"):
        if not skills_dir.exists():
            continue
        for skill_dir in sorted(skills_dir.iterdir(), key=lambda path: path.name):
            if skill_dir.name in seen:
                continue
            if (skill_dir / "SKILL.md").exists():
                names.append(skill_dir.name)
                seen.add(skill_dir.name)
    return names


def _write_co_ai_entrypoint(path: Path, *, model: str, max_iterations: int, agent_name: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    model_literal = json.dumps(model)
    name_literal = json.dumps(agent_name)
    path.write_text(
        "\n".join([
            "import sys",
            "from pathlib import Path",
            "",
            "PACKAGE_ROOT = Path(__file__).resolve().parents[2]",
            "sys.path.insert(0, str(PACKAGE_ROOT))",
            "CO_DIR = PACKAGE_ROOT / \".co\"",
            "",
            "from connectonion import host",
            "from connectonion.cli.co_ai.agent import create_coding_agent",
            "",
            "",
            "def create_agent():",
            "    return create_coding_agent(",
            f"        name={name_literal},",
            f"        model={model_literal},",
            f"        max_iterations={max_iterations},",
            "        auto_approve=True,",
            "        co_dir=CO_DIR,",
            "        browser_headless=True,",
            "        browser_channel=\"chrome\",",
            "    )",
            "",
            "",
            "host(create_agent, trust=\"careful\", co_dir=CO_DIR)",
            "",
        ]),
        encoding="utf-8",
    )


def _make_tarball(source_dir: Path, tarball_path: Path) -> None:
    with tarfile.open(tarball_path, "w:gz") as tar:
        for path in sorted(source_dir.rglob("*")):
            tar.add(path, arcname=str(path.relative_to(source_dir)))


def _copy_connectonion_package(staging_dir: Path) -> None:
    shutil.copytree(
        PACKAGE_ROOT,
        staging_dir / "connectonion",
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".pytest_cache"),
    )


def _copy_connectonion_project_metadata(staging_dir: Path) -> bool:
    """Copy local package metadata when deploying from a source checkout."""
    pyproject = PROJECT_ROOT / "pyproject.toml"
    if not pyproject.exists():
        return False

    shutil.copy2(pyproject, staging_dir / "pyproject.toml")
    for filename in ("README.md", "LICENSE"):
        source = PROJECT_ROOT / filename
        if source.exists():
            shutil.copy2(source, staging_dir / filename)
    return True


def _write_co_ai_requirements(
    staging_dir: Path,
    *,
    install_local_package: bool,
    skill_requirements: list[Path] | None = None,
) -> None:
    lines = ["." if install_local_package else f"connectonion=={__version__}"]
    for requirement_path in sorted(skill_requirements or []):
        lines.append(f"-r {requirement_path.relative_to(staging_dir).as_posix()}")
    (staging_dir / "requirements.txt").write_text(
        "\n".join(lines) + "\n",
        encoding="utf-8",
    )


def _write_co_ai_dockerfile(staging_dir: Path, *, install_local_package: bool) -> None:
    lines = [
        "FROM python:3.11-slim",
        "WORKDIR /app",
        "ENV PYTHONUNBUFFERED=1",
        "ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright",
    ]
    if install_local_package:
        lines.extend([
            "COPY pyproject.toml README.md requirements.txt ./",
            "COPY connectonion ./connectonion",
            "COPY .co ./.co",
        ])
    else:
        lines.extend([
            "COPY requirements.txt ./",
            "COPY connectonion ./connectonion",
            "COPY .co ./.co",
        ])
    lines.extend([
        "RUN pip install --no-cache-dir -r requirements.txt",
        "RUN python -m playwright install --with-deps chrome",
        "ENV PORT=8000",
        f"CMD [\"python\", \"{CO_AI_ENTRYPOINT}\"]",
        "",
    ])
    (staging_dir / "Dockerfile").write_text("\n".join(lines), encoding="utf-8")


def create_co_ai_deploy_package(
    *,
    project_dir: Path,
    skills: list[str],
    all_skills: bool,
    project_name: str,
    model: str,
    max_iterations: int,
) -> DeployPackage:
    """Build a self-contained co-ai deploy tarball."""
    temp_dir = Path(tempfile.mkdtemp())
    tarball_path = temp_dir / "agent.tar.gz"
    staging_dir = temp_dir / "staging"
    staging_dir.mkdir()

    _copy_connectonion_package(staging_dir)
    install_local_package = _copy_connectonion_project_metadata(staging_dir)
    _write_co_ai_entrypoint(
        staging_dir / CO_AI_ENTRYPOINT,
        model=model,
        max_iterations=max_iterations,
        agent_name=project_name,
    )

    deploy_skill_names = []
    seen_skill_names = set()
    for skill_name in discover_deploy_skill_names(project_dir) if all_skills else []:
        deploy_skill_names.append(skill_name)
        seen_skill_names.add(skill_name)
    for skill_name in skills:
        if skill_name not in seen_skill_names:
            deploy_skill_names.append(skill_name)
            seen_skill_names.add(skill_name)

    skill_requirement_files = []
    for skill_name in deploy_skill_names:
        source = resolve_deploy_skill(skill_name, project_dir)
        destination = staging_dir / ".co" / "skills" / skill_name
        if destination.exists():
            shutil.rmtree(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(source, destination)
        requirements_file = destination / "requirements.txt"
        if requirements_file.exists():
            skill_requirement_files.append(requirements_file)

    _write_co_ai_requirements(
        staging_dir,
        install_local_package=install_local_package,
        skill_requirements=skill_requirement_files,
    )
    _write_co_ai_dockerfile(staging_dir, install_local_package=install_local_package)

    _make_tarball(staging_dir, tarball_path)
    return DeployPackage(tarball_path=tarball_path, entrypoint=CO_AI_ENTRYPOINT)
