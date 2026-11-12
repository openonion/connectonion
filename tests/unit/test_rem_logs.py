import json
import socket
import subprocess
import sys

from typer.testing import CliRunner

from connectonion.cli.main import app
from connectonion.rem.files import state_path, write_json


def test_rem_logs_shows_interrupted_for_a_dead_local_run(tmp_path):
    process = subprocess.Popen([sys.executable, "-c", "pass"])
    assert process.wait() == 0
    run_id = "run_" + "a" * 32
    write_json(state_path(tmp_path, f"runs/{run_id}.json"), {
        "id": run_id, "started_at": "2026-01-01T00:00:00+00:00",
        "outcome": "running", "host": socket.gethostname(), "pid": process.pid,
    })

    runner = CliRunner()
    arguments = ["rem", "--root", str(tmp_path)]
    result = runner.invoke(app, [*arguments, "logs"])
    assert result.exit_code == 0, result.output
    assert "interrupted" in result.output
    result = runner.invoke(app, [*arguments, "--json", "logs"])
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["data"][0]["outcome"] == "interrupted"
