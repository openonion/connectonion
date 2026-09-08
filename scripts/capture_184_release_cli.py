"""Capture account-free help from two explicitly installed release artifacts."""
import argparse
import io
import os
from pathlib import Path
import subprocess
import sys
import tempfile

from rich.console import Console
from rich.text import Text


def capture(import_root: Path, destination: Path, expected_version: str) -> None:
    console = Console(record=True, width=100, force_terminal=False, file=io.StringIO())
    with tempfile.TemporaryDirectory(prefix="co-release-help-") as temporary:
        config = Path(temporary) / "config"
        config.mkdir()
        environment = {
            "PATH": os.defpath,
            "PYTHONPATH": str(import_root.resolve()),
            "AGENT_CONFIG_PATH": str(config),
            "NO_COLOR": "1",
            "COLUMNS": "100",
        }
        version = subprocess.check_output(
            [sys.executable, "-c", "import connectonion; print(connectonion.__version__)"],
            cwd=temporary, env=environment, text=True, timeout=30,
        ).strip()
        if version != expected_version:
            raise ValueError(f"Expected {expected_version}, found {version}")
        for args in (("--version",), ("gmail", "draft", "--help"), ("syno", "--help")):
            result = subprocess.run(
                [sys.executable, "-m", "connectonion.cli.main", *args],
                cwd=temporary, env=environment, capture_output=True, text=True,
                check=True, timeout=30,
            )
            console.print("$ co " + " ".join(args), style="bold cyan")
            console.print(Text.from_ansi(result.stdout))
    console.save_svg(str(destination), title=f"ConnectOnion {version} · installed CLI help")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline-import-root", required=True, type=Path)
    parser.add_argument("--candidate-import-root", required=True, type=Path)
    parser.add_argument("--candidate-version", default="1.8.4a1")
    args = parser.parse_args()
    destination = Path(__file__).resolve().parents[1] / "docs/releases/assets" / ("v" + args.candidate_version)
    destination.mkdir(parents=True, exist_ok=True)
    capture(args.baseline_import_root, destination / "cli-before.svg", "1.8.3")
    capture(args.candidate_import_root, destination / "cli-after.svg", args.candidate_version)


if __name__ == "__main__":
    main()
