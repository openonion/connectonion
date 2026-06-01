"""
Purpose: Deploy agent projects to ConnectOnion Cloud with git archive packaging and env vars
LLM-Note:
  Dependencies: imports from [os, subprocess, tempfile, time, yaml, requests, pathlib, rich.console, dotenv] | imported by [cli/main.py via handle_deploy()] | calls backend at [https://oo.openonion.ai/api/v1/deploy]
  Data flow: handle_deploy() → validates git repo and .co/host.yaml → load_api_key() loads OPENONION_API_KEY → reads host.yaml for project name, entrypoint, env file path → dotenv_values() loads env vars from .env → git archive creates tarball of HEAD → POST to /api/v1/deploy with tarball + project_name + env_vars → polls /api/v1/deploy/{id}/status until running/error → displays agent URL
  State/Effects: creates temporary tarball file in tempdir | reads .co/host.yaml, .env files | makes network POST request | prints progress to stdout via rich.Console | does not modify project files
  Integration: exposes handle_deploy() for CLI | expects git repo with .co/host.yaml (name, entrypoint, env) | uses Bearer token auth | returns void (prints results)
  Performance: git archive is fast | network timeout 600s for upload, 10s for status checks | polls every 3s up to 100 times (~5 min)
  Errors: fails if not git repo | fails if not ConnectOnion project (no host.yaml) | fails if no API key | prints backend error messages
"""

import json
import os
import re
import shutil
import subprocess
import tarfile
import tempfile
import time
import yaml
import requests
from dataclasses import dataclass
from pathlib import Path
from rich.console import Console
from dotenv import dotenv_values

from connectonion import __version__
from .project_cmd_lib import load_api_key

console = Console()

API_BASE = "https://oo.openonion.ai"
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


def _archive_git_head(project_dir: Path, tarball_path: Path, *, gzip: bool) -> None:
    fmt = "tar.gz" if gzip else "tar"
    subprocess.run(
        ["git", "archive", f"--format={fmt}", "-o", str(tarball_path), "HEAD"],
        cwd=project_dir,
        check=True,
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


def create_deploy_package(
    *,
    project_dir: Path,
    template: str,
    skills: list[str],
    all_skills: bool = False,
    project_name: str,
    entrypoint: str,
    model: str,
    max_iterations: int,
) -> DeployPackage:
    """Build the tarball sent to the deploy API."""
    temp_dir = Path(tempfile.mkdtemp())
    tarball_path = temp_dir / "agent.tar.gz"

    if template == "project":
        _archive_git_head(project_dir, tarball_path, gzip=True)
        return DeployPackage(tarball_path=tarball_path, entrypoint=entrypoint)

    if template != "co-ai":
        raise DeployConfigError("Unsupported deploy template. Use 'project' or 'co-ai'.")

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


def resolve_deploy_template(
    template: str,
    skill_names: list[str],
    project_dir: Path,
    *,
    all_skills: bool = False,
) -> str:
    """Resolve the user-facing deploy mode."""
    if template == "auto":
        if skill_names or all_skills:
            return "co-ai"
        if (project_dir / ".git").exists() or (project_dir / ".co" / "host.yaml").exists():
            return "project"
        return "co-ai"

    if template in ("project", "co-ai"):
        return template

    raise DeployConfigError("Unsupported deploy template. Use 'auto', 'project', or 'co-ai'.")


def _check_host_export(entrypoint: str) -> bool:
    """Check if entrypoint file exports an ASGI app via host().

    Looks for patterns like:
    - host(agent)
    - host(my_agent)
    - from connectonion import host
    """
    entrypoint_path = Path(entrypoint)
    if not entrypoint_path.exists():
        return False

    content = entrypoint_path.read_text()

    # Check for host() call pattern
    # Matches: host(agent), host(my_agent), host( agent ), etc.
    host_call_pattern = r'\bhost\s*\([^)]+\)'

    if re.search(host_call_pattern, content):
        return True

    return False


def handle_deploy(
    name: str | None = None,
    template: str = "auto",
    skills: list[str] | None = None,
    all_skills: bool = False,
    model: str = "co/gemini-3-flash-preview",
    max_iterations: int = 100,
):
    """Deploy agent to ConnectOnion Cloud."""
    console.print("\n[cyan]Deploying to ConnectOnion Cloud...[/cyan]\n")

    project_dir = Path.cwd()
    skill_names = parse_skill_names(skills)

    try:
        deploy_template = resolve_deploy_template(
            template,
            skill_names,
            project_dir,
            all_skills=all_skills,
        )
    except DeployConfigError as e:
        console.print(f"[red]{e}[/red]")
        return

    if deploy_template == "project" and skill_names:
        console.print("[red]--skills requires --template co-ai[/red]")
        return
    if deploy_template == "project" and all_skills:
        console.print("[red]--all-skills requires --template co-ai[/red]")
        return

    host_yaml_path = Path(".co") / "host.yaml"
    config = {}

    if deploy_template == "project":
        # Must be a git repo
        if not (project_dir / ".git").exists():
            console.print("[red]Not a git repository. Run 'git init' first.[/red]")
            return

        # Must be a ConnectOnion project
        if not host_yaml_path.exists():
            console.print("[red]Not a ConnectOnion project. Run 'co init' first.[/red]")
            return

    # Must have API key
    api_key = load_api_key()
    if not api_key:
        console.print("[red]No API key. Run 'co auth' first.[/red]")
        return

    if host_yaml_path.exists():
        with open(host_yaml_path, 'r') as f:
            config = yaml.safe_load(f) or {}

    if name is not None:
        project_name = validate_deploy_name(name)
    elif deploy_template == "co-ai":
        project_name = "co-ai"
    else:
        project_name = config.get("name", "unnamed-agent")
    env_file = config.get("env", ".env")
    entrypoint = config.get("entrypoint", "agent.py" if deploy_template == "project" else CO_AI_ENTRYPOINT)

    if deploy_template == "project":
        # Validate entrypoint exists
        if not Path(entrypoint).exists():
            console.print(f"[red]Entrypoint not found: {entrypoint}[/red]")
            console.print("[dim]Set 'entrypoint' in .co/host.yaml[/dim]")
            return

        # Validate entrypoint exports ASGI app via host()
        if not _check_host_export(entrypoint):
            console.print(f"[red]Entrypoint '{entrypoint}' does not export an ASGI app.[/red]")
            console.print()
            console.print("[yellow]To deploy, your agent must call host():[/yellow]")
            console.print()
            console.print("  [cyan]from connectonion import Agent, host[/cyan]")
            console.print()
            console.print("  [cyan]agent = Agent('my-agent', ...)[/cyan]")
            console.print("  [cyan]host(agent)  # Starts HTTP server[/cyan]")
            console.print()
            console.print("[dim]See: https://docs.connectonion.com/deploy[/dim]")
            return

    # Load env vars from .env (user's API keys, config for the agent container)
    env_vars = load_deploy_env_vars(env_file)
    if deploy_template == "co-ai" and api_key and "OPENONION_API_KEY" not in env_vars:
        env_vars["OPENONION_API_KEY"] = api_key

    try:
        package = create_deploy_package(
            project_dir=project_dir,
            template=deploy_template,
            skills=skill_names,
            all_skills=all_skills,
            project_name=project_name,
            entrypoint=entrypoint,
            model=model,
            max_iterations=max_iterations,
        )
    except DeployConfigError as e:
        console.print(f"[red]{e}[/red]")
        return

    # Show package size
    tarball_path = package.tarball_path
    upload_entrypoint = package.entrypoint
    tarball_size = tarball_path.stat().st_size
    if tarball_size < 1024:
        size_str = f"{tarball_size} B"
    elif tarball_size < 1024 * 1024:
        size_str = f"{tarball_size / 1024:.1f} KB"
    else:
        size_str = f"{tarball_size / (1024 * 1024):.2f} MB"

    console.print(f"  Project: {project_name}")
    console.print(f"  Package: {size_str}")
    console.print(f"  Env vars: {len(env_vars)} keys")
    console.print()

    # Upload
    console.print("Uploading...")
    serialized_env_vars = json.dumps(env_vars)
    with open(tarball_path, "rb") as f:
        response = requests.post(
            f"{API_BASE}/api/v1/deploy",
            files={"package": ("agent.tar.gz", f, "application/gzip")},
            data={
                "project_name": project_name,
                "env_vars": serialized_env_vars,
                "secrets": serialized_env_vars,
                "entrypoint": upload_entrypoint,
            },
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=600,  # 10 minutes for docker build
        )

    if response.status_code != 200:
        console.print(f"[red]Deploy failed: {response.text}[/red]")
        return

    result = response.json()

    # Check for error response (backend returns 200 with error dict)
    if "error" in result:
        console.print(f"[red]Deploy failed: {result['error']}[/red]")
        return

    deployment_id = result.get("id")
    url = result.get("url", "")

    # Wait for deployment
    console.print("Building...")
    deploy_success = False
    final_status = "unknown"
    timeout_count = 0

    for _ in range(100):
        try:
            status_resp = requests.get(
                f"{API_BASE}/api/v1/deploy/{deployment_id}/status",
                headers={"Authorization": f"Bearer {api_key}"},
                timeout=30,  # Increased timeout for slow SSH
            )
        except requests.exceptions.Timeout:
            timeout_count += 1
            if timeout_count >= 3:
                console.print("[yellow]Status checks timing out, but deploy may still succeed.[/yellow]")
                break
            time.sleep(3)
            continue
        except requests.exceptions.RequestException as e:
            console.print(f"[yellow]Network error: {e}[/yellow]")
            time.sleep(3)
            continue

        if status_resp.status_code != 200:
            console.print(f"[red]Status check failed: {status_resp.status_code}[/red]")
            break

        result = status_resp.json()
        final_status = result.get("status", "unknown")

        if final_status == "running":
            deploy_success = True
            # Update URL from status response (may be more up-to-date)
            url = result.get("url") or url
            break
        if final_status in ("error", "failed"):
            console.print(f"[red]Deploy failed: {result.get('error_message') or 'Unknown error'}[/red]")
            return
        time.sleep(3)

    console.print()
    if deploy_success:
        console.print("[bold green]Deployed![/bold green]")
    else:
        console.print(f"[yellow]Deploy status: {final_status}[/yellow]")
        console.print("[yellow]Check status with 'co deployments' or try again.[/yellow]")

    # Always show URL if we have one
    if url:
        console.print(f"Agent URL: {url}")

    # Always fetch and display container logs
    if deployment_id:
        logs_resp = requests.get(
            f"{API_BASE}/api/v1/deploy/{deployment_id}/logs?tail=20",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=10,
        )
        if logs_resp.status_code == 200:
            logs = logs_resp.json().get("logs", "")
            if logs:
                console.print()
                console.print("[dim]Container logs:[/dim]")
                console.print(f"[dim]{logs}[/dim]")

    console.print()
