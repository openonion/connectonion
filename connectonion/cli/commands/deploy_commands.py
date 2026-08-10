"""
Purpose: Deploy agent projects to ConnectOnion Cloud with local packaging and env vars
LLM-Note:
  Dependencies: imports from [fnmatch, json, os, re, shutil, subprocess, tarfile, tempfile, time, yaml, requests, pathlib, rich.console, dotenv] | imported by [cli/main.py via handle_deploy()] | calls the configured backend /api/v1/deploy
  Data flow: handle_deploy() → optionally creates a temporary template project via co create (named by --name, default {template}-agent) → validates .co/host.yaml → reads host.yaml for project name, entrypoint, env file path → checks the name against DEPLOY_NAME_PATTERN (same rule the backend enforces) and _exports_asgi_app() on the entrypoint → load_api_key() loads OPENONION_API_KEY → dotenv_values() loads env vars from .env → packages git-tracked files or initialized folder into tarball, merging each --skills path into .co/skills/ (a path that is itself a skill nests under its dirname) → POST to /api/v1/deploy with tarball + project_name + env_vars → polls /api/v1/deploy/{id}/status until running/error → displays agent URL
  State/Effects: creates temporary tarball file in tempdir | template deploy creates/deletes a temporary project on success | reads .co/host.yaml, .env files | makes network POST request | prints progress to stdout via rich.Console | normal deploy does not modify project files
  Integration: exposes handle_deploy(template, skills, name) for CLI | expects .co/host.yaml (name, entrypoint, env) unless --template is used | --name only valid with --template (otherwise the name comes from host.yaml) | uses Bearer token auth | returns bool success
  Performance: packaging is local file I/O | network timeout 600s for upload, 30s for status checks | polls every 3s for up to 20 min, covering the backend's own build budget (rsync 120s + docker build 900s + run 60s)
  Errors: fails if not ConnectOnion project (no host.yaml) | fails if project name is not a valid hostname label | fails if no API key | prints backend error messages
"""

import fnmatch
import json
import re
import shutil
import subprocess
import io
import tarfile
import tempfile
import time
import yaml
import requests
import typer
from pathlib import Path
from rich.console import Console
from dotenv import dotenv_values
from ...backend import backend_url

from .project_cmd_lib import (
    GITIGNORE_CONTENT,
    DEPLOY_NAME_PATTERN,
    load_api_key,
    normalize_deploy_name,
)

console = Console()

DASHBOARD_URL = "https://o.openonion.ai/dashboard"

# Poll until the backend's own build budget is exhausted (rsync 120s + docker
# build 900s + run 60s), plus slack for queueing. Giving up at 5 minutes told
# users a co-ai or browser deploy had failed while it was still building.
DEPLOY_POLL_SECONDS = 3
DEPLOY_TIMEOUT_SECONDS = 20 * 60


def _exports_asgi_app(entrypoint: str) -> bool:
    """Check if entrypoint file exports an ASGI app via host().

    Looks for patterns like:
    - host(agent)
    - host(my_agent)
    - from connectonion import host
    """
    entrypoint_path = Path(entrypoint)
    if not entrypoint_path.exists():
        return False

    content = entrypoint_path.read_text(encoding="utf-8")

    # Blank out single-line string literals first. The comment rule below is
    # lexical, so without this a `#` inside a string would hide a real call
    # later on the same line (`msg = "note: #1"; host(agent)`) and block a valid
    # deploy. Triple-quoted strings are left alone — a `#` inside one followed
    # by a host() call on the same physical line is not a real scenario, and a
    # pre-flight check is not worth a tokenizer.
    content = re.sub(r'"[^"\n]*"|\'[^\'\n]*\'', '""', content)

    # `[^#\n]*` keeps commented-out calls from counting. The lookbehind rules out
    # names that merely end in "host" (ghost(...), localhost(...)) but allows a
    # leading dot, so `connectonion.host(agent)` still counts — wrongly blocking
    # a valid deploy is worse than letting one through to a clear container error.
    host_call_pattern = r'^[^#\n]*(?<![A-Za-z0-9_])host\s*\([^)]+\)'

    if re.search(host_call_pattern, content, re.MULTILINE):
        return True

    return False


def _load_deploy_ignore_patterns(project_dir: Path) -> list[str]:
    """Use ConnectOnion's default .gitignore plus the project's .gitignore."""
    lines = GITIGNORE_CONTENT.splitlines()
    gitignore = project_dir / ".gitignore"
    if gitignore.exists():
        lines.extend(gitignore.read_text(encoding="utf-8").splitlines())
    return [line.strip() for line in lines if line.strip() and not line.lstrip().startswith("#")]


def _load_skill_ignore_patterns(skill_dir: Path) -> list[str]:
    """What to leave out of a skill, which is not a project.

    A skill's `build/` is a compiled helper it shells out to; its `todo.md` may
    be a document it reads. The project defaults call both of those noise, so a
    skill bundled with them lost files silently — the deploy succeeded and the
    skill failed later, on the server, reaching for something that was never
    sent.

    Only a `.gitignore` the skill's own author wrote applies here, plus the
    caches nobody means to ship — and secrets, which are the one thing the
    project defaults were right about. `.env*` and `.co/keys/` leave the machine
    over a network to a server, so they never travel, whatever the skill wants.
    """
    lines = ["__pycache__/", "*.py[cod]", ".DS_Store", ".git/",
             ".env*", ".co/keys/", "*.pem", "id_rsa", "id_ed25519"]
    gitignore = skill_dir / ".gitignore"
    if gitignore.exists():
        lines.extend(gitignore.read_text(encoding="utf-8").splitlines())
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


def _error_text(response: requests.Response) -> str:
    """Backend errors are {"detail": "..."}; fall back to the raw body."""
    try:
        detail = response.json().get("detail")
    except ValueError:
        return response.text
    if isinstance(detail, str):
        return detail
    return response.text


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
    for path in _deployable_directory_files(source, ignore_patterns):
        source_rel = path.relative_to(source)
        rel = arc_prefix / source_rel
        tar.add(path, arcname=str(rel), recursive=False)


def _deployable_directory_files(
    source: Path, ignore_patterns: list[str]
) -> list[Path]:
    """Files the directory packer will really add, in stable order."""
    return [
        path
        for path in sorted(source.rglob("*"))
        if path.is_file()
        and not _is_ignored_for_deploy(path.relative_to(source), ignore_patterns)
    ]


def _project_files_for_deploy(
    project_dir: Path, ignore_patterns: list[str]
) -> list[Path]:
    """Project source files under the exact git/non-git packaging rules."""
    if _is_git_repo(project_dir):
        return [
            project_dir / rel
            for rel in sorted(_iter_git_tracked_files(project_dir))
            if (project_dir / rel).is_file()
            and not _is_ignored_for_deploy(rel, ignore_patterns)
        ]
    return _deployable_directory_files(project_dir, ignore_patterns)


def _add_deployer_as_admin(tar: tarfile.TarFile, project_dir: Path) -> None:
    """Ship the admin list: whoever the project names, plus the deployer.

    A deployed agent generates its own keypair on first boot, and ADMIN_ADD is gated
    on super-admin — which is that same address, whose private key never leaves the
    server. So nobody could ever become admin: the only account that could grant it
    is the one nobody can sign as.

    The public address is enough to break that: the agent recognises it in its admin
    list and grants the role to whoever signs as it. Nothing secret travels, and
    revoking is deleting a line. Same idea as ssh-copy-id, one layer up.

    Written into the package on every deploy so the list self-heals.

    Merged with the project's own .co/admins.txt rather than replacing it. That
    file is packed with the rest of the project — only some of .co/ is excluded,
    not all of it — so this used to add a *second* member with the same path,
    and extraction took the last one. Anyone the operator had added was dropped,
    silently, and the loss surfaced later as a colleague who could not command an
    agent they had been given access to. One entry now, and it contains both.

    The identity resolved is the one `co call` signs with — project .co/ first, then
    ~/.co/ — and deliberately not `project_dir/.co`: a --template deploy builds a
    throwaway project whose address is deleted with it, so seeding that would name an
    admin nobody can ever be.
    """
    from ... import address
    from .keys_commands import _find_co_dir

    co_dir = _find_co_dir()
    if not co_dir:
        return
    data = address.load(co_dir)
    if not data or not data.get("address"):
        return

    admins = []
    configured = project_dir / ".co" / "admins.txt"
    if configured.exists():
        admins = [l.strip() for l in configured.read_text(encoding="utf-8").splitlines()
                  if l.strip()]
    if data["address"] not in admins:
        admins.append(data["address"])

    payload = ("\n".join(admins) + "\n").encode()
    info = tarfile.TarInfo(name=".co/admins.txt")
    info.size = len(payload)
    info.mode = 0o600
    tar.addfile(info, io.BytesIO(payload))


def _warn_about_skills_left_behind(project_dir: Path, skills_paths: list[Path]) -> None:
    """Name the skills that work here and will not exist on the server.

    A user-tier skill (~/.co/skills, ~/.claude/skills) is usually a symlink into a
    separate repo, which is invisible to anything that packages a project. So it can
    look installed, work for months, and be absent everywhere else — and the agent
    then behaves differently for a reason nothing in its output explains.

    A warning, not a failure: leaving a personal skill behind is often exactly what
    the operator wants. The cost is only that it happens silently.
    """
    from ...useful_plugins.skills import skills_that_will_not_travel

    bundled = set()
    for path in skills_paths:
        if (path / "SKILL.md").exists():
            bundled.add(path.name)
        else:
            bundled.update(
                child.name
                for child in path.iterdir()
                if child.is_dir() and (child / "SKILL.md").exists()
            )
    staying = [s for s in skills_that_will_not_travel(project_dir=project_dir)
               if s.name not in bundled]

    if staying:
        console.print(
            f"  [yellow]![/yellow] {len(staying)} skill(s) stay on this machine: "
            + ", ".join(s.name for s in staying[:5])
            + (f" (+{len(staying) - 5} more)" if len(staying) > 5 else "")
        )
        console.print("    [dim]co skills list  ·  move one into .co/skills/ to ship it[/dim]")

    ignored = _load_deploy_ignore_patterns(project_dir)
    payload_entries = {
        path.absolute() for path in _project_files_for_deploy(project_dir, ignored)
    }
    for path in skills_paths:
        payload_entries.update(
            source.absolute()
            for source in _deployable_directory_files(
                path, _load_skill_ignore_patterns(path)
            )
        )
    _print_deploy_skill_problems(
        project_dir,
        console,
        payload_entries=payload_entries,
    )


def _print_deploy_skill_problems(
    project_dir: Path,
    output: Console,
    *,
    payload_entries: set[Path] | None = None,
    payload_roots: tuple[Path, ...] = (),
) -> None:
    """Show a real repair path; only payload problems look like deploy failures."""
    from rich.markup import escape
    from ...useful_plugins.skills import find_skill_problem_details

    entries = payload_entries or set()

    def is_in_payload(path: Path) -> bool:
        # Cloud entries are files, while a skill problem names its directory.
        # Explicit --skills paths are resolved before they reach this function,
        # while diagnosis deliberately preserves the repairable symlink path.
        candidates = {path, path.resolve(strict=False)}
        for candidate in candidates:
            for entry in entries:
                try:
                    entry.relative_to(candidate)
                    return True
                except ValueError:
                    pass
            for root in payload_roots:
                try:
                    candidate.relative_to(root)
                    return True
                except ValueError:
                    pass
        return False

    for problem in find_skill_problem_details(project_dir=project_dir):
        affects_payload = is_in_payload(problem.path)
        color, marker = ("red", "✗") if affects_payload else ("yellow", "!")
        target = f" → {escape(str(problem.target))}" if problem.target is not None else ""
        scope = "affects this deploy" if affects_payload else "not in deploy payload"
        output.print(
            f"  [{color}]{marker}[/{color}] {escape(str(problem.path))} — "
            f"{escape(problem.reason)}{target} "
            f"[dim]({escape(problem.location)}; {scope})[/dim]",
            soft_wrap=True,
        )


def _build_tarball(project_dir: Path, skills_paths: list[Path]) -> Path:
    """Package git-tracked files when available, otherwise the initialized folder.

    .env is read separately as deploy secrets and is never included in the package.
    External --skills directories are copied into .co/skills/.
    """
    ignore_patterns = _load_deploy_ignore_patterns(project_dir)
    # _add_deployer_as_admin writes this path itself, having merged the
    # project's copy with the deployer. Packing the file here as well would put
    # two members under one name and let write order decide which survives.
    ignore_patterns.append(".co/admins.txt")
    ignore_patterns.extend([
        ".co/skill-requirements.requested.json",
        ".co/skill-python-requirements.txt",
    ])
    tarball = Path(tempfile.mkdtemp()) / "agent.tar.gz"
    with tarfile.open(tarball, "w:gz") as tar:
        for path in _project_files_for_deploy(project_dir, ignore_patterns):
            tar.add(path, arcname=str(path.relative_to(project_dir)), recursive=False)
        for skills_path in skills_paths:
            # A path is either one skill (has SKILL.md) or a directory of skills.
            arc_prefix = Path(".co") / "skills"
            if (skills_path / "SKILL.md").exists():
                arc_prefix = arc_prefix / skills_path.name
            _add_directory_to_tarball(
                tar,
                skills_path,
                arc_prefix,
                _load_skill_ignore_patterns(skills_path),
            )

        from ...skill_deploy import collect_deploy_skill_requirements

        skill_requirements = collect_deploy_skill_requirements(project_dir, skills_paths)
        requested = json.dumps(
            {**skill_requirements.requested_state, "digest": skill_requirements.digest},
            indent=2,
        ).encode()
        info = tarfile.TarInfo(name=".co/skill-requirements.requested.json")
        info.size = len(requested)
        info.mode = 0o644
        tar.addfile(info, io.BytesIO(requested))

        python_requirements = ("\n".join(skill_requirements.python) + "\n").encode()
        info = tarfile.TarInfo(name=".co/skill-python-requirements.txt")
        info.size = len(python_requirements)
        info.mode = 0o644
        tar.addfile(info, io.BytesIO(python_requirements))
        _add_deployer_as_admin(tar, project_dir)
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
    # `co create` reports an unknown template by exiting 1; deploy reports it by
    # returning False, so the two conventions have to be translated here.
    try:
        handle_create(
            name=project_name,
            ai=None,
            key=None,
            template=template,
            description=None,
            yes=True,
            parent_dir=temp_root,
        )
    except typer.Exit:
        shutil.rmtree(temp_root, ignore_errors=True)
        return False

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

    # The project, not the directory you ran from -- see _read_project.
    from ...project import project_root

    project_dir = project_root() if project_dir is None else project_dir

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

    from ...skill_deploy import collect_deploy_skill_requirements

    skill_requirements = collect_deploy_skill_requirements(project_dir, skills_paths)
    if skill_requirements.unsupported:
        console.print("[red]Cloud deploy cannot realize these required skill dependencies:[/red]")
        for requirement in skill_requirements.unsupported:
            console.print(f"  [red]✗[/red] {requirement}")
        return False

    # Load config from host.yaml. The project is checked before credentials are:
    # a broken host.yaml is worth reporting whether or not you happen to be
    # logged in.
    with open(host_yaml_path, 'r', encoding="utf-8") as f:
        config = yaml.safe_load(f) or {}
    # host.yaml is hand-editable and YAML types values for you: an unquoted
    # `name: 123` arrives as an int, and matching a regex against it raises
    # TypeError — a traceback in place of the clear message below. Coerce to str
    # so a hand-edited file fails cleanly, or works when the value is sensible.
    project_name = str(config.get("name") or "unnamed-agent")
    env_file = str(config.get("env") or ".env")
    entrypoint = str(config.get("entrypoint") or "agent.py")

    # The name becomes a hostname and a Docker tag, so the backend rejects
    # anything outside this set. `co init` now normalizes it when writing
    # host.yaml, but an older project or a hand-edited file can still carry a
    # bad one — catch it here rather than after packaging and uploading.
    if not DEPLOY_NAME_PATTERN.match(project_name):
        console.print(f"[red]Invalid project name: {project_name}[/red]")
        console.print(
            "[dim]Names may use 1-39 lowercase letters, digits, and hyphens, "
            "and must start with a letter or digit.[/dim]"
        )
        # Offer the corrected form rather than leaving the user to derive it.
        suggestion = normalize_deploy_name(project_name)
        if suggestion:
            console.print(f"[dim]Try:  name: {suggestion}[/dim]")
        console.print(f"[dim]Set 'name' in {host_yaml_path}[/dim]")
        return False

    # Validate entrypoint exists
    entrypoint_path = project_dir / entrypoint
    if not entrypoint_path.exists():
        console.print(f"[red]Entrypoint not found: {entrypoint}[/red]")
        console.print("[dim]Set 'entrypoint' in .co/host.yaml[/dim]")
        return False

    # Validate entrypoint exports ASGI app via host()
    if not _exports_asgi_app(str(entrypoint_path)):
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

    # Must have API key
    api_key = load_api_key()
    if not api_key:
        console.print("[red]No API key. Run 'co auth' first.[/red]")
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
    _warn_about_skills_left_behind(project_dir, skills_paths)

    tarball_size = tarball_path.stat().st_size
    size_str = _format_bytes(tarball_size)

    console.print(f"  Project: {project_name}")
    console.print(f"  Source: {project_dir}")
    console.print(f"  Package: {size_str} ({_count_packaged_files(tarball_path)} files)")
    console.print(f"  Env: {env_path} ({len(env_vars)} keys)")
    if skills_paths:
        console.print("  Skills:")
        for skills_path in skills_paths:
            # Mirror _build_tarball: a path that is itself a skill nests under its name.
            dest = f".co/skills/{skills_path.name}/" if (skills_path / "SKILL.md").exists() else ".co/skills/"
            console.print(f"    {skills_path} -> {dest}")
    console.print()

    deploy_data = {
        "project_name": project_name,
        "secrets": json.dumps(env_vars),
        "entrypoint": entrypoint,
    }
    api_base = backend_url()
    console.print(f"Uploading package to {api_base}...")
    with console.status("[cyan]Uploading package...[/cyan]"):
        with open(tarball_path, "rb") as f:
            response = requests.post(
                f"{api_base}/api/v1/deploy",
                files={"package": ("agent.tar.gz", f, "application/gzip")},
                data=deploy_data,
                headers={"Authorization": f"Bearer {api_key}"},
                timeout=600,  # 10 minutes for docker build
            )

    if response.status_code != 200:
        console.print(f"[red]Deploy failed: {_error_text(response)}[/red]")
        return False

    result = response.json()

    # Check for error response (backend returns 200 with error dict)
    if "error" in result:
        console.print(f"[red]Deploy failed: {result['error']}[/red]")
        return False

    deployment_id = result.get("id")
    url = result.get("url", "")
    if not deployment_id:
        # Without an id there is nothing to poll; don't spend five minutes
        # requesting /deploy/None/status.
        console.print("[red]Deploy failed: backend did not return a deployment id[/red]")
        return False
    console.print(f"Deployment: {deployment_id}")

    # Wait for deployment
    console.print("Building container on ConnectOnion Cloud...")
    deploy_success = False
    final_status = "unknown"
    timeout_count = 0

    deadline = time.monotonic() + DEPLOY_TIMEOUT_SECONDS

    while time.monotonic() < deadline:
        try:
            status_resp = requests.get(
                f"{api_base}/api/v1/deploy/{deployment_id}/status",
                headers={"Authorization": f"Bearer {api_key}"},
                timeout=30,  # Increased timeout for slow SSH
            )
        except requests.exceptions.Timeout:
            timeout_count += 1
            if timeout_count >= 3:
                console.print("[yellow]Status checks timing out, but deploy may still succeed.[/yellow]")
                break
            time.sleep(DEPLOY_POLL_SECONDS)
            continue
        except requests.exceptions.RequestException as e:
            console.print(f"[yellow]Network error: {e}[/yellow]")
            time.sleep(DEPLOY_POLL_SECONDS)
            continue

        if status_resp.status_code != 200:
            console.print(f"[red]Status check failed: {status_resp.status_code}[/red]")
            break

        result = status_resp.json()
        final_status = result.get("status", "unknown")
        # Clamp: a status call that returns near the deadline makes this
        # negative, and -5 seconds formats as "-1m55s left" (// floors, % does
        # not) rather than anything a reader can use.
        remaining = max(0, int(deadline - time.monotonic()))
        console.print(f"  [{remaining // 60}m{remaining % 60:02d}s left] status: {final_status}")

        if final_status == "running":
            deploy_success = True
            # Update URL from status response (may be more up-to-date)
            url = result.get("url") or url
            break
        if final_status in ("error", "failed"):
            console.print(f"[red]Deploy failed: {result.get('error_message') or 'Unknown error'}[/red]")
            return False
        time.sleep(DEPLOY_POLL_SECONDS)

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

    # Show the agent's startup logs (best-effort). deployment_id is always set
    # here — the missing-id case returned above.
    time.sleep(5)  # "running" fires when the container starts; wait for the app to print its banner or crash
    try:
        logs_resp = requests.get(
            f"{backend_url()}/api/v1/deploy/{deployment_id}/logs?tail=20",
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
