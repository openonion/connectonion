"""Both env files must load — a project .env must never hide ~/.co/keys.env.

Importing connectonion runs the env loading once per process, so these tests
drive it in a subprocess with a controlled cwd and HOME.
"""

import subprocess
import sys
import textwrap


def _run_import(tmp_path, project_env: str, keys_env: str, probe: str) -> str:
    """Import connectonion with a fake cwd/HOME and print one env var."""
    home = tmp_path / "home"
    (home / ".co").mkdir(parents=True)
    (home / ".co" / "keys.env").write_text(keys_env)

    project = tmp_path / "project"
    project.mkdir()
    if project_env is not None:
        (project / ".env").write_text(project_env)

    script = textwrap.dedent(f"""
        import os, sys
        sys.path.insert(0, {str(project.parent.parent)!r})
        import connectonion  # noqa: F401
        print(os.getenv({probe!r}, "<missing>"))
    """)

    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=project,
        env={"HOME": str(home), "PATH": "/usr/bin:/bin", "PYTHONPATH": _repo_root()},
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    return result.stdout.strip()


def _repo_root() -> str:
    from pathlib import Path
    return str(Path(__file__).resolve().parents[2])


def test_keys_env_still_loads_when_project_env_exists(tmp_path):
    """The regression: OAuth tokens live in keys.env and were invisible."""
    value = _run_import(
        tmp_path,
        project_env="OPENAI_API_KEY=sk-project\n",
        keys_env="GOOGLE_ACCESS_TOKEN=from-keys-env\n",
        probe="GOOGLE_ACCESS_TOKEN",
    )
    assert value == "from-keys-env"


def test_project_env_wins_over_keys_env(tmp_path):
    """Project-specific values still override the global fallback."""
    value = _run_import(
        tmp_path,
        project_env="OPENAI_API_KEY=sk-project\n",
        keys_env="OPENAI_API_KEY=sk-global\n",
        probe="OPENAI_API_KEY",
    )
    assert value == "sk-project"


def test_keys_env_loads_when_no_project_env(tmp_path):
    value = _run_import(
        tmp_path,
        project_env=None,
        keys_env="OPENAI_API_KEY=sk-global\n",
        probe="OPENAI_API_KEY",
    )
    assert value == "sk-global"
