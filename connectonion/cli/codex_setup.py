"""Install OpenAI's Codex CLI and attempt OAuth without holding up global init."""
import json
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import httpx

from .. import codex_cli
from ..codex_cli import INSTALL_COMMAND, resolve_codex

INSTALL_URL = "https://chatgpt.com/codex/install.sh"


def _run_install(command, **kwargs):
    result = subprocess.run(command, capture_output=True, text=True, timeout=300,
                            stdin=subprocess.DEVNULL, **kwargs)
    if result.returncode:
        raise RuntimeError((result.stderr or result.stdout or "installer failed").strip()[-500:])


def _version(path):
    result = subprocess.run([path, "--version"], capture_output=True, text=True, timeout=15)
    if result.returncode or not result.stdout.strip():
        raise RuntimeError("installed Codex did not pass --version")
    return result.stdout.strip().removeprefix("codex-cli ")


def _install_standalone():
    """The official installer verifies SHA-256 release digests before installing.

    Source: openai/codex/scripts/install/install.sh. Fetch via HTTPS from the
    README's official URL; run the saved script rather than a shell pipeline.
    """
    response = httpx.get(INSTALL_URL, follow_redirects=True, timeout=30)
    response.raise_for_status()
    directory = Path.home() / ".local/bin"
    environment = {**os.environ, "CODEX_NON_INTERACTIVE": "true", "CODEX_INSTALL_DIR": str(directory)}
    with tempfile.TemporaryDirectory(prefix="co-codex-") as temporary:
        script = Path(temporary) / "install.sh"
        script.write_bytes(response.content)
        _run_install(["sh", str(script)], env=environment)
    path = directory / "codex"
    if not path.is_file() or not os.access(path, os.X_OK):
        raise RuntimeError(f"installer did not create an executable at {path}")
    home = Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex").expanduser()
    undo = (f"rm -f {shlex.quote(str(path))} {shlex.quote(str(directory / 'codex-code-mode-host'))}; "
            f"rm -rf {shlex.quote(str(home / 'packages/standalone'))}; "
            "remove the '# >>> Codex installer >>>' block from your shell profile")
    return str(path), _version(str(path)), undo


def install_codex() -> tuple[str, str, str]:
    """Prefer the standalone installer; package managers are optional fallbacks."""
    failures = []
    try:
        return _install_standalone()
    except (httpx.HTTPError, OSError, subprocess.SubprocessError, RuntimeError) as error:
        failures.append(str(error))
    managers = [("npm", ["install", "-g", "@openai/codex"], "npm uninstall -g @openai/codex")]
    if sys.platform == "darwin":
        managers.append(("brew", ["install", "--cask", "codex"], "brew uninstall --cask codex"))
    for manager, args, undo in managers:
        command = shutil.which(manager)
        if not command:
            continue
        try:
            _run_install([command, *args], env={**os.environ, "NONINTERACTIVE": "1"})
            path = resolve_codex()
            if not path:
                raise RuntimeError(f"{manager} installed Codex but its executable was not found")
            return path, _version(path), undo
        except (OSError, subprocess.SubprocessError, RuntimeError) as error:
            failures.append(f"{manager}: {error}")
    raise RuntimeError("; ".join(failures))


def _login(command):
    if codex_cli.signed_in(command):
        return True
    print("Opening Codex login in your browser; init continues if sign-in is unfinished.")
    try:
        subprocess.run([*command, "login"], stdin=subprocess.DEVNULL, timeout=45)
    except (OSError, subprocess.TimeoutExpired, KeyboardInterrupt):
        # A browser may be unavailable, the user may cancel, or OAuth may take
        # longer. Only this optional login step is interrupted; init goes on.
        return codex_cli.signed_in(command)
    return codex_cli.signed_in(command)


def claude_ready() -> bool:
    """A fallback must be authenticated, not merely installed."""
    from ..useful_tools.claude_code import _base_command
    from ..rem.runner import child_env
    command = _base_command()
    if not command:
        return False
    try:
        result = subprocess.run([*command, "auth", "status", "--json"], env=child_env({"runner": "claude-code"}),
                                stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=15)
        return result.returncode == 0 and json.loads(result.stdout).get("loggedIn") is True
    except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError):
        return False


def _existing_undo(path):
    for app in ("ChatGPT", "Codex"):
        if path.startswith(f"/Applications/{app}.app/"):
            return f"Reused the bundled CLI; uninstall {app}.app to remove it."
    return f"Reused an existing CLI; remove with its package manager or rm -f {shlex.quote(path)}"


def setup_codex() -> dict:
    from ..useful_tools.codex import _base_command
    command = _base_command()
    if command:
        command = command[:-1]
        summary = f"Codex CLI: found at {command[0]}"
        undo = _existing_undo(command[0])
    else:
        try:
            path, version, undo = install_codex()
        except RuntimeError as error:
            return {"ready": False, "summary": f"Codex CLI: not installed: {error}; run {INSTALL_COMMAND}",
                    "undo": "No Codex CLI installation completed.", "next_action": INSTALL_COMMAND,
                    "login_command": "codex login"}
        command = [path]
        summary = f"Codex CLI: installed {version} at {path}"
    login = shlex.join([*command, "login"])
    return {"ready": _login(command), "summary": summary, "undo": undo,
            "login_command": login, "next_action": login}
