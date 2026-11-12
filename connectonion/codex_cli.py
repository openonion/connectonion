"""Locate the same Codex CLI for interactive tools, init and scheduled turns."""
import os
import shutil
import subprocess
from pathlib import Path


BUNDLED_CODEX = (
    Path("/Applications/ChatGPT.app/Contents/Resources/codex-cli/bin/codex"),
    Path("/Applications/Codex.app/Contents/Resources/codex-cli/CodexCLI.app/Contents/MacOS/codex"),
)
INSTALL_COMMAND = "curl -fsSL https://chatgpt.com/codex/install.sh | CODEX_NON_INTERACTIVE=true sh"


def resolve_codex(*, path: str | None = None) -> str | None:
    """PATH wins, then desktop bundles, then our standalone install off PATH."""
    found = shutil.which("codex", path=path) if path is not None else shutil.which("codex")
    if found:
        return os.path.abspath(found)
    for path in (*BUNDLED_CODEX, Path.home() / ".local/bin/codex"):
        if path.is_file() and os.access(path, os.X_OK):
            return str(path)
    return None


def signed_in(command: list[str]) -> bool:
    """Ask the CLI: auth may live in a keychain, and auth.json may be stale."""
    try:
        result = subprocess.run([*command, "login", "status"], stdin=subprocess.DEVNULL,
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=15)
        return result.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False
