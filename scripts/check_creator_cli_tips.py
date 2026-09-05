"""Audit creator CLI tips, help parity and exit codes using synthetic responses.

Model calls receive only command output and a goal. Replies are graded as text;
no generated command is executed. Use the installed candidate wheel interpreter,
or pass --source to exercise a checkout. No real API or browser is used.
"""

import argparse
from contextlib import redirect_stderr, redirect_stdout
import io
import json
import os
import re
import shlex
import subprocess
import sys
import tempfile
from pathlib import Path


def _plan(output: str) -> dict:
    return json.loads(next(line.split("\t", 1)[1] for line in output.splitlines() if line.startswith("plan\t")))


def _upload_next(output: str) -> str:
    plan = _plan(output)
    snippet = plan["body"]["snippet"]
    return shlex.join(["co", "youtube", "put", plan["file"]["path"], "--title", snippet["title"],
        "--channel", plan["channel_id"], "--description", snippet["description"],
        "--privacy", plan["body"]["status"]["privacyStatus"], "--category", snippet["categoryId"],
        "--confirm", plan["confirmation"]])


def _update_next(output: str) -> str:
    plan = _plan(output)
    return shlex.join(["co", "youtube", "update", plan["body"]["id"], "--title",
        plan["body"]["snippet"]["title"], "--confirm", plan["confirmation"]])


def _capture(fixture, command, environment, directory, mode):
    environment = {**environment, "CREATOR_CLI_FIXTURE_MODE": mode}
    with subprocess.Popen([sys.executable, str(fixture), *command], stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE, env=environment, cwd=directory) as producer:
        piped = subprocess.run(["cat"], stdin=producer.stdout, capture_output=True, text=True, timeout=45)
        producer.stdout.close()
        producer.wait(timeout=45)
        stderr = producer.stderr.read().decode("utf-8", errors="replace")
        return producer.returncode, piped.stdout, stderr


def _markdown(report: dict) -> str:
    def cell(value):
        return str(value).replace("|", "\\|").replace("\n", "<br>")
    lines = ["## CLI skill audit", "", f"Model: `{report['model']}`. Synthetic fixtures; replies were never executed.", "",
             "| command | tip printed | goal given to the fresh agent | it replied | pass |",
             "|---|---|---|---|---|"]
    for row in report["tips"]:
        lines.append("| " + " | ".join(cell(value) for value in [row["command"], row["tip"], row["goal"], row.get("reply", "not run"), row.get("tip_pass", "not run")]) + " |")
    lines += ["", "| exit | provoked by | printed | names a next command |", "|---|---|---|---|"]
    for row in report["exits"]:
        lines.append("| " + " | ".join(cell(value) for value in [row["exit"], row["invocation"], row["output"].strip(), row["next_command"]]) + " |")
    lines += ["", "| group | CLI help | skill | difference |", "|---|---|---|---|"]
    for provider, row in report["parity"].items():
        lines.append(f"| {provider} | {', '.join(row['cli'])} | {', '.join(row['skill'])} | none |")
    lines += ["", "All seven creator leaves are covered. Bare `co youtube` is the list alias; bare TikTok and `--help` are routing/help views. External `co auth` and `co browser` commands are dependencies, not new creator leaves. The Google prerequisite's exit-0 failure is reproduced above and called out at the start of the skill.", ""]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--markdown", type=Path)
    parser.add_argument("--source", action="store_true")
    parser.add_argument("--tip-model", help="Explicit opt-in to a text-only model call for each leaf output")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    fixture = root / "tests/creator_browser/cli-fixture.py"
    environment = {**os.environ, "PYTHON_DOTENV_DISABLED": "1"}
    if args.source:
        environment["PYTHONPATH"] = str(root)
        sys.path.insert(0, str(root))
    else:
        environment.pop("PYTHONPATH", None)
    report = {"model": args.tip_model, "tips": [], "exits": [], "parity": {}}
    with tempfile.TemporaryDirectory(prefix="creator-tip-") as directory:
        clip = Path(directory) / "fixture.mp4"
        clip.write_bytes(b"Synthetic fixture: never uploaded")
        channel = "UC" + "a" * 22
        cases = [
            (["youtube", "channel"], "List the channel's uploads.", f"co youtube list {channel}", 0),
            (["youtube", "list"], "Inspect the first video in this listing.", "co youtube video 1", 0),
            (["youtube", "video", "Abcdefgh_01"], "Read this video's channel.", f"co youtube channel {channel}", 0),
            (["youtube", "put", str(clip), "--title", "Demo", "--channel", channel], "The user approved this exact preview. Upload the shown video with its reviewed metadata.", _upload_next, 0),
            (["youtube", "update", "Abcdefgh_01", "--title", "New title"], "The user approved this exact preview. Apply the shown title change.", _update_next, 0),
            (["tiktok", "post", str(clip), "--caption", "Demo", "--account", "@creator"], "Find your owned browser tab before checking TikTok readiness.", "co browser tab ls", 0),
            (["tiktok", "inspect", "--tab", "creator-tiktok"], "Check the current page before asking the user to log in.", "co browser -t creator-tiktok get_current_url", 1),
        ]
        for command, goal, expected, exit_code in cases:
            actual_exit, output, stderr = _capture(fixture, command, environment, directory, "normal")
            assert actual_exit == exit_code and not stderr, "Unexpected CLI exit/stderr; details withheld"
            expected = expected(output) if callable(expected) else expected
            assert "--help" not in shlex.split(expected), "An action tip cannot pass by asking for help"
            tip = output.splitlines()[-1]
            assert tip.endswith(expected), f"Missing final tip for {command[:2]}"
            row = {"command": "co " + " ".join(command[:2]), "exit": exit_code,
                   "output": output, "tip": tip, "goal": goal, "expected": expected, "pipe_pass": True}
            if args.tip_model:
                from connectonion import llm_do
                try:
                    with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                        reply = llm_do(f"You just ran a shell command. Its full output was:\n\n{output}\n\n"
                                       f"Your goal: {goal} Reply with ONE shell command and nothing else.", model=args.tip_model)
                    row.update(reply=reply.strip(), tip_pass=shlex.split(reply.strip()) == shlex.split(expected))
                except Exception:
                    row.update(tip_pass=False, error="Text-only model call failed; details withheld")
            report["tips"].append(row)
        exit_cases = [
            (["youtube", "list"], "normal", 0, "co youtube video 1", "Abcdefgh_01"),
            (["youtube", "list"], "missing_google", 1, "co auth google --youtube", "auth_required"),
            (["youtube", "video", "1"], "normal", 1, "co youtube list", "stale_number"),
            (["tiktok", "inspect", "--tab", "creator-tiktok"], "normal", 1, "co browser -t creator-tiktok get_current_url", "login_required"),
            (["youtube", "video"], "normal", 2, "co youtube video --help", "Missing argument"),
            (["youtube", "list", "-n", "201"], "normal", 2, "co youtube list --help", "Invalid value"),
            (["tiktok", "inspect"], "normal", 2, "co tiktok inspect --help", "Missing option"),
            (["auth", "google", "--youtube"], "normal", 0, "co auth", "Not authenticated with OpenOnion"),
        ]
        for command, mode, expected_exit, next_command, cause in exit_cases:
            exit_code, output, stderr = _capture(fixture, command, environment, directory, mode)
            assert exit_code == expected_exit and not stderr and cause in output and next_command in output
            report["exits"].append({"invocation": shlex.join(["co", *command]) + f" (fixture: {mode})",
                                    "exit": exit_code, "output": output, "next_command": next_command})
        from typer.main import get_command
        from connectonion.cli.main import app
        from connectonion import __file__ as package_file
        skill = (Path(package_file).parent / "useful_skills/co-creator/SKILL.md").read_text()
        for provider in ["youtube", "tiktok"]:
            commands = sorted(get_command(app).commands[provider].commands)
            documented = sorted(set(re.findall(rf"co {provider} ([a-z][a-z-]+)", skill)))
            exit_code, output, stderr = _capture(fixture, [provider, "--help"], environment, directory, "normal")
            assert exit_code == 0 and not stderr and commands == documented and all(name in output for name in commands)
            report["parity"][provider] = {"cli": commands, "skill": documented, "pass": True}
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    if args.markdown:
        args.markdown.write_text(_markdown(report), encoding="utf-8")
    passed = sum(row.get("tip_pass", False) for row in report["tips"]) if args.tip_model else None
    print(json.dumps({"pipe_pass": len(report["tips"]), "total": len(report["tips"]), "tip_pass": passed,
                      "exit_cases": len(report["exits"]), "parity": True, "output": str(args.output)}))
    return 0 if all(row.get("tip_pass", True) for row in report["tips"]) else 1


if __name__ == "__main__":
    raise SystemExit(main())
