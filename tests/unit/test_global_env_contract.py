"""The selected env file is independent of cwd, including package startup."""

import json
import os
import shlex
from pathlib import Path
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def layout(tmp_path):
    home = tmp_path / "home"
    (home / ".co").mkdir(parents=True)
    (home / ".co" / "keys.env").write_text(
        "MODEL=global\nGLOBAL_ONLY=yes\nGOOGLE_ACCESS_TOKEN=global-token\n"
        "GOOGLE_EMAIL=global@example.test\nGOOGLE_SCOPES=gmail.readonly\n"
    )
    project = tmp_path / "project"
    (project / ".co").mkdir(parents=True)
    (project / ".env").write_text(
        "MODEL=project\nPROJECT_ONLY=yes\nGOOGLE_ACCESS_TOKEN=project-token\n"
        "GOOGLE_EMAIL=project@example.test\n"
    )
    nested = project / "src"
    nested.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    return home, project, nested, outside


def probe(layout, cwd, *, selected=None, overrides=None):
    home, *_ = layout
    env = {"HOME": str(home), "USERPROFILE": str(home),
           "PATH": os.environ.get("PATH", ""), "PYTHONPATH": str(ROOT)}
    env.update(overrides or {})
    script = "import connectonion\n"
    if selected is not None:
        script += (
            "from connectonion.cli.main import app\n"
            "@app.command('probe-env')\n"
            "def probe_env():\n"
            "    import json, os\n"
            "    print(json.dumps(dict(os.environ)))\n"
            f"app(['--env-file', {str(selected)!r}, 'probe-env'])\n"
        )
    else:
        script += "import json, os; print(json.dumps(dict(os.environ)))\n"
    return subprocess.run([sys.executable, "-c", script], cwd=cwd, env=env,
                          capture_output=True, text=True, timeout=30)


@pytest.mark.parametrize("index", [1, 2, 3])
def test_default_ignores_all_project_settings(layout, index):
    result = probe(layout, layout[index])
    assert result.returncode == 0, result.stderr
    values = json.loads(result.stdout)
    assert values["MODEL"] == "global"
    assert values["GOOGLE_ACCESS_TOKEN"] == "global-token"
    assert "PROJECT_ONLY" not in values


@pytest.mark.parametrize("index", [1, 2, 3])
def test_explicit_file_replaces_global_without_mixing_records(layout, index):
    result = probe(layout, layout[index], selected=layout[1] / ".env")
    assert result.returncode == 0, result.stderr
    values = json.loads(result.stdout)
    assert values["MODEL"] == "project"
    assert values["GOOGLE_ACCESS_TOKEN"] == "project-token"
    assert values["GOOGLE_EMAIL"] == "project@example.test"
    assert "GOOGLE_SCOPES" not in values
    assert "GLOBAL_ONLY" not in values


def test_process_token_selects_whole_process_record(layout):
    result = probe(layout, layout[2], overrides={"GOOGLE_ACCESS_TOKEN": "process-token"})
    assert result.returncode == 0, result.stderr
    values = json.loads(result.stdout)
    assert values["GOOGLE_ACCESS_TOKEN"] == "process-token"
    assert "GOOGLE_EMAIL" not in values
    assert "GOOGLE_SCOPES" not in values


def test_selected_file_preserves_inherited_settings(layout):
    result = probe(layout, layout[2], selected=layout[1] / ".env",
                   overrides={"MODEL": "shell", "GOOGLE_ACCESS_TOKEN": "shell-token"})
    assert result.returncode == 0, result.stderr
    values = json.loads(result.stdout)
    assert values["MODEL"] == "shell"
    assert values["GOOGLE_ACCESS_TOKEN"] == "shell-token"
    assert "GOOGLE_EMAIL" not in values


def test_custom_global_path_ignores_routing_inside_env(layout):
    home, project, _, outside = layout
    custom = home / "custom"
    custom.mkdir()
    (custom / "keys.env").write_text(f"MODEL=custom\nAGENT_CONFIG_PATH={project}\n")
    result = probe(layout, outside, overrides={"AGENT_CONFIG_PATH": str(custom)})
    values = json.loads(result.stdout)
    assert values["MODEL"] == "custom"
    assert values["AGENT_CONFIG_PATH"] == str(custom)


@pytest.mark.parametrize("name", ["absent.env", ".co"])
def test_invalid_explicit_file_fails_before_command(layout, name):
    result = probe(layout, layout[2], selected=layout[1] / name)
    assert result.returncode == 2
    # The tip keeps the selector and names `co env`, the command that runs on
    # a file nothing else can use — not `co --help`, which repairs nothing.
    output = result.stderr + result.stdout
    selector = shlex.quote(str((layout[1] / name).resolve()))
    assert f"Next: co --env-file {selector} env" in output
    assert "global-token" not in output


def test_malformed_explicit_file_does_not_print_credentials(layout):
    path = layout[1] / "broken.env"
    path.write_text('GOOGLE_ACCESS_TOKEN="secret-unclosed\n')
    result = probe(layout, layout[2], selected=path)
    assert result.returncode == 2
    assert "invalid syntax on line 1" in result.stdout + result.stderr
    assert "secret-unclosed" not in result.stdout + result.stderr
    assert "global-token" not in result.stdout + result.stderr


def test_cli_can_select_valid_file_even_when_global_file_is_malformed(layout):
    home, project, _, outside = layout
    (home / '.co' / 'keys.env').write_text('GOOGLE_ACCESS_TOKEN="broken-global-secret\n')
    result = subprocess.run([sys.executable, '-m', 'connectonion.cli.main',
                             '--env-file', str(project / '.env'), 'keys'],
                            cwd=outside, env={'HOME': str(home), 'USERPROFILE': str(home),
                             'PATH': os.environ.get('PATH', ''), 'PYTHONPATH': str(ROOT)},
                            capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stdout + result.stderr
    assert 'broken-global-secret' not in result.stdout + result.stderr
