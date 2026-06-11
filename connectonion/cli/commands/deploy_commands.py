"""
Purpose: Deploy agent projects to ConnectOnion Cloud with local packaging and env vars
LLM-Note:
  Dependencies: imports from [fnmatch, json, os, re, shutil, subprocess, tarfile, tempfile, time, yaml, requests, pathlib, rich.console, dotenv] | imported by [cli/main.py via handle_deploy()] | calls backend at [https://oo.openonion.ai/api/v1/deploy]
  Data flow: handle_deploy() → optionally creates a temporary template project via co create (named by --name, default {template}-agent) → validates .co/host.yaml → load_api_key() loads OPENONION_API_KEY → reads host.yaml for project name, entrypoint, env file path → dotenv_values() loads env vars from .env → packages git-tracked files or initialized folder into tarball, merging each --skills path into .co/skills/ (a path that is itself a skill nests under its dirname) → POST to /api/v1/deploy with tarball + project_name + env_vars → polls /api/v1/deploy/{id}/status until running/error → displays agent URL
  State/Effects: creates temporary tarball file in tempdir | template deploy creates/deletes a temporary project on success | reads .co/host.yaml, .env files | makes network POST request | prints progress to stdout via rich.Console | normal deploy does not modify project files
  Integration: exposes handle_deploy(template, skills, name) for CLI | expects .co/host.yaml (name, entrypoint, env) unless --template is used | --name only valid with --template (otherwise the name comes from host.yaml) | uses Bearer token auth | returns bool success
  Performance: packaging is local file I/O | network timeout 600s for upload, 30s for status checks | polls every 3s up to 100 times (~5 min)
  Errors: fails if not ConnectOnion project (no host.yaml) | fails if no API key | prints backend error messages
"""

import fnmatch
import json
import re
import shutil
import subprocess
import tarfile
import tempfile
import time
import yaml
import requests
from pathlib import Path
from rich.console import Console
from dotenv import dotenv_values

from .project_cmd_lib import GITIGNORE_CONTENT, load_api_key

console = Console()

API_BASE = "https://oo.openonion.ai"
DASHBOARD_URL = "https://o.openonion.ai/dashboard"


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


def _load_deploy_ignore_patterns(project_dir: Path) -> list[str]:
    """Use ConnectOnion's default .gitignore plus the project's .gitignore."""
    lines = GITIGNORE_CONTENT.splitlines()
    gitignore = project_dir / ".gitignore"
    if gitignore.exists():
        lines.extend(gitignore.read_text().splitlines())
    return [line.strip() for line in lines if line.strip() and not line.lstrip().startswith("#")]


def _path_matches_ignore_pattern(rel: Path, pattern: str) -> bool:
    rel_text = rel.as_posix()
    pattern = pattern.lstrip("/")

    if pattern.endswith("/"):
        dirname = pattern.rstrip("/")
        if "/" in dirname:
            return rel_text == dirname or rel_text.startswith(dirname + "/")
        return dirname in rel.parts

    if "/" in pattern:
        return fnmatch.fnmatch(rel_text, pattern)
    return fnmatch.fnmatch(rel.name, pattern)


def _is_ignored_for_deploy(rel: Path, ignore_patterns: list[str]) -> bool:
    return any(_path_matches_ignore_pattern(rel, pattern) for pattern in ignore_patterns)


def _iter_git_tracked_files(project_dir: Path) -> list[Path]:
    """Return tracked files, using current working-tree contents."""
    result = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=project_dir,
        check=True,
        capture_output=True,
    )
    return [
        Path(raw.decode())
        for raw in result.stdout.split(b"\0")
        if raw
    ]


def _is_git_repo(project_dir: Path) -> bool:
    if not (project_dir / ".git").exists():
        return False
    result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        cwd=project_dir,
        capture_output=True,
    )
    return result.returncode == 0 and Path(result.stdout.decode().strip()).resolve() == project_dir.resolve()


def _format_bytes(size: int) -> str:
    if size < 1024:
        return f"{size} B"
    if size < 1024 * 1024:
        return f"{size / 1024:.1f} KB"
    return f"{size / (1024 * 1024):.2f} MB"


def _count_packaged_files(tarball: Path) -> int:
    with tarfile.open(tarball) as tar:
        return len([member for member in tar.getmembers() if member.isfile()])


def _add_directory_to_tarball(
    tar: tarfile.TarFile,
    source: Path,
    arc_prefix: Path,
    ignore_patterns: list[str],
) -> None:
    for path in sorted(source.rglob("*")):
        if not path.is_file():
            continue
        source_rel = path.relative_to(source)
        if _is_ignored_for_deploy(source_rel, ignore_patterns):
            continue
        rel = arc_prefix / source_rel
        tar.add(path, arcname=str(rel), recursive=False)


def _build_tarball(project_dir: Path, skills_paths: list[Path]) -> Path:
    """Package git-tracked files when available, otherwise the initialized folder.

    .env is read separately as deploy secrets and is never included in the package.
    External --skills directories are copied into .co/skills/.
    """
    ignore_patterns = _load_deploy_ignore_patterns(project_dir)
    tarball = Path(tempfile.mkdtemp()) / "agent.tar.gz"
    with tarfile.open(tarball, "w:gz") as tar:
        if _is_git_repo(project_dir):
            for rel in sorted(_iter_git_tracked_files(project_dir)):
                if _is_ignored_for_deploy(rel, ignore_patterns):
                    continue
                path = project_dir / rel
                if path.is_file():
                    tar.add(path, arcname=str(rel), recursive=False)
        else:
            for path in sorted(project_dir.rglob("*")):
                if not path.is_file():
                    continue
                rel = path.relative_to(project_dir)
                if _is_ignored_for_deploy(rel, ignore_patterns):
                    continue
                tar.add(path, arcname=str(rel), recursive=False)
        for skills_path in skills_paths:
            # A path is either one skill (has SKILL.md) or a directory of skills.
            arc_prefix = Path(".co") / "skills"
            if (skills_path / "SKILL.md").exists():
                arc_prefix = arc_prefix / skills_path.name
            _add_directory_to_tarball(
                tar,
                skills_path,
                arc_prefix,
                _load_deploy_ignore_patterns(skills_path),
            )
    return tarball


def _deploy_template_project(template: str, skills: list[str], name: str | None = None) -> bool:
    """Create a temporary template project, deploy it, and clean up on success."""
    temp_root = Path.cwd() / ".tmp" / "connectonion-deploy"
    if temp_root.exists():
        shutil.rmtree(temp_root)
    temp_root.mkdir(parents=True)
    project_name = name or f"{template}-agent"
    project_dir = temp_root / project_name

    console.print(f"[cyan]Creating temporary {template} project...[/cyan]")
    from .create import handle_create

    # Reuse the normal project creation path so template deploy stays in sync
    # with `co create --template <name> -y` and does not mutate cwd.
    handle_create(
        name=project_name,
        ai=None,
        key=None,
        template=template,
        description=None,
        yes=True,
        parent_dir=temp_root,
    )

    if not (project_dir / ".co" / "host.yaml").exists():
        console.print(f"[red]Template project creation did not produce a deployable project: {project_dir}[/red]")
        shutil.rmtree(temp_root)
        return False

    success = _deploy_current_project(skills, project_dir)

    if success:
        shutil.rmtree(temp_root)
    else:
        # Keep failed template deploys inspectable; otherwise users lose build context.
        console.print(f"[yellow]Temporary deploy project kept for debugging: {project_dir}[/yellow]")
    return success


def _deploy_current_project(skills: list[str], project_dir: Path | None = None) -> bool:
    """Deploy the current ConnectOnion project."""
    console.print("\n[cyan]Deploying to ConnectOnion Cloud...[/cyan]\n")

    project_dir = Path.cwd() if project_dir is None else project_dir

    # Must be a ConnectOnion project
    host_yaml_path = project_dir / ".co" / "host.yaml"

    if not host_yaml_path.exists():
        console.print("[red]Not a ConnectOnion project. Run 'co init' first.[/red]")
        return False

    # `--skills PATH` means "copy this folder into remote .co/skills".
    # Resolve here so template deploys can pass paths from the original cwd.
    skills_paths = [Path(s).expanduser().resolve() for s in (skills or [])]
    for sp in skills_paths:
        if not sp.is_dir():
            console.print(f"[red]Skills path not found or not a directory: {sp}[/red]")
            return False

    # Must have API key
    api_key = load_api_key()
    if not api_key:
        console.print("[red]No API key. Run 'co auth' first.[/red]")
        return False

    # Load config from host.yaml
    with open(host_yaml_path, 'r') as f:
        config = yaml.safe_load(f) or {}
    project_name = config.get("name", "unnamed-agent")
    env_file = config.get("env", ".env")
    entrypoint = config.get("entrypoint", "agent.py")

    # Validate entrypoint exists
    entrypoint_path = project_dir / entrypoint
    if not entrypoint_path.exists():
        console.print(f"[red]Entrypoint not found: {entrypoint}[/red]")
        console.print("[dim]Set 'entrypoint' in .co/host.yaml[/dim]")
        return False

    # Validate entrypoint exports ASGI app via host()
    if not _check_host_export(str(entrypoint_path)):
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
        return False

    # Load env vars from .env as runtime secrets; .env itself stays out of the tarball.
    env_path = project_dir / env_file
    env_vars = dotenv_values(env_path) if env_path.exists() else {}

    # AGENT_CONFIG_PATH in .env points at the deployer's local ~/.co (an absolute
    # host path). Inside the container the bundled .co lands at /app/.co, so rewrite
    # it — never ship a local host path as a runtime secret.
    if env_vars.get("AGENT_CONFIG_PATH"):
        env_vars["AGENT_CONFIG_PATH"] = "/app/.co"

    # Package source. Git projects upload tracked files with current working-tree
    # contents; non-git projects upload the initialized folder. Either way .env is
    # sent as secrets below, never included in the tarball, and --skills merge in.
    tarball_path = _build_tarball(project_dir, skills_paths)

    tarball_size = tarball_path.stat().st_size
    size_str = _format_bytes(tarball_size)

    console.print(f"  Project: {project_name}")
    console.print(f"  Source: {project_dir}")
    console.print(f"  Package: {size_str} ({_count_packaged_files(tarball_path)} files)")
    console.print(f"  Env: {env_path} ({len(env_vars)} keys)")
    if skills_paths:
        console.print("  Skills:")
        for skills_path in skills_paths:
            console.print(f"    {skills_path} -> .co/skills/")
    console.print()

    deploy_data = {
        "project_name": project_name,
        "secrets": json.dumps(env_vars),
        "entrypoint": entrypoint,
    }
    console.print(f"Uploading package to {API_BASE}...")
    with console.status("[cyan]Uploading package...[/cyan]"):
        with open(tarball_path, "rb") as f:
            response = requests.post(
                f"{API_BASE}/api/v1/deploy",
                files={"package": ("agent.tar.gz", f, "application/gzip")},
                data=deploy_data,
                headers={"Authorization": f"Bearer {api_key}"},
                timeout=600,  # 10 minutes for docker build
            )

    if response.status_code != 200:
        console.print(f"[red]Deploy failed: {response.text}[/red]")
        return False

    result = response.json()

    # Check for error response (backend returns 200 with error dict)
    if "error" in result:
        console.print(f"[red]Deploy failed: {result['error']}[/red]")
        return False

    deployment_id = result.get("id")
    url = result.get("url", "")
    if deployment_id:
        console.print(f"Deployment: {deployment_id}")

    # Wait for deployment
    console.print("Building container on ConnectOnion Cloud...")
    deploy_success = False
    final_status = "unknown"
    timeout_count = 0

    for attempt in range(100):
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
        console.print(f"  [{attempt + 1}/100] status: {final_status}")

        if final_status == "running":
            deploy_success = True
            # Update URL from status response (may be more up-to-date)
            url = result.get("url") or url
            break
        if final_status in ("error", "failed"):
            console.print(f"[red]Deploy failed: {result.get('error_message') or 'Unknown error'}[/red]")
            return False
        time.sleep(3)

    if deploy_success:
        console.print("[bold green]Deployed![/bold green]")
    else:
        console.print(f"[yellow]Deploy status: {final_status}[/yellow]")
        console.print("[yellow]Check status with 'co status' or try again.[/yellow]")

    # Always show URL if we have one
    if url:
        console.print(f"Agent URL: {url}")
    if deploy_success:
        console.print(f"Dashboard: {DASHBOARD_URL}")

    # Show the agent's startup logs (best-effort).
    if deployment_id:
        time.sleep(5)  # "running" fires when the container starts; wait for the app to print its banner or crash
        try:
            logs_resp = requests.get(
                f"{API_BASE}/api/v1/deploy/{deployment_id}/logs?tail=20",
                headers={"Authorization": f"Bearer {api_key}"},
                timeout=10,
            )
        except requests.exceptions.RequestException:
            logs_resp = None
        if logs_resp is not None and logs_resp.status_code == 200:
            logs = logs_resp.json().get("logs", "")
            if logs:
                console.print()
                console.print("[dim]Container logs:[/dim]")
                console.print(f"[dim]{logs}[/dim]")

    console.print()
    return deploy_success


def handle_deploy(template: str | None = None, skills: list[str] | None = None, name: str | None = None):
    """Deploy agent to ConnectOnion Cloud."""
    skills = skills or []
    if template:
        absolute_skills = [str(Path(s).expanduser().resolve()) for s in skills]
        return _deploy_template_project(template, absolute_skills, name)
    if name:
        console.print("[red]--name only applies to template deploys; project name comes from .co/host.yaml[/red]")
        return False
    return _deploy_current_project(skills)
