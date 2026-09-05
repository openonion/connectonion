"""Pipe every creator leaf through cat; optionally grade tips with text-only llm_do.

Provider responses are synthetic. A tip-model call never receives tools and
its returned command is recorded, never executed. Run with the candidate wheel
interpreter to exercise the installed package; pass --source for a checkout.
"""

import argparse
from contextlib import redirect_stderr, redirect_stdout
import io
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--source", action="store_true")
    parser.add_argument("--tip-model", help="Explicit opt-in to a text-only model call for each output")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    fixture = root / "tests/creator_browser/cli-fixture.py"
    environment = {**os.environ, "PYTHON_DOTENV_DISABLED": "1"}
    if args.source:
        environment["PYTHONPATH"] = str(root)
    else:
        environment.pop("PYTHONPATH", None)
    results = []
    with tempfile.TemporaryDirectory(prefix="creator-tip-") as directory:
        clip = Path(directory) / "fixture.mp4"
        clip.write_bytes(b"Synthetic fixture: never uploaded")
        cases = [
            (["youtube", "channel"], "List the channel's uploads.", "co youtube list UC" + "a" * 22 + "", 0),
            (["youtube", "list"], "Inspect the first video in this listing.", "co youtube video 1", 0),
            (["youtube", "video", "Abcdefgh_01"], "Read this video's channel.", "co youtube channel UC" + "a" * 22 + "", 0),
            (["youtube", "put", str(clip), "--title", "Demo", "--channel", "UC" + "a" * 22], "Read the confirmation options before deciding whether to upload.", "co youtube put --help", 0),
            (["youtube", "update", "Abcdefgh_01", "--title", "New title"], "Read the confirmation options before deciding whether to change the video.", "co youtube update --help", 0),
            (["tiktok", "post", str(clip), "--caption", "Demo", "--account", "@creator"], "Read the browser inspection prerequisites.", "co tiktok inspect --help", 0),
            (["tiktok", "inspect", "--tab", "creator-tiktok"], "Check the current page before asking the user to log in.", "co browser -t creator-tiktok get_current_url", 1),
        ]
        for command, goal, expected, exit_code in cases:
            with subprocess.Popen([sys.executable, str(fixture), *command], stdout=subprocess.PIPE,
                                  stderr=subprocess.PIPE, env=environment, cwd=directory) as producer:
                piped = subprocess.run(["cat"], stdin=producer.stdout, capture_output=True, text=True, timeout=45)
                producer.stdout.close()
                producer.wait(timeout=45)
                assert producer.returncode == exit_code, "Unexpected CLI exit; fixture details withheld"
            output = piped.stdout
            tip = output.splitlines()[-1]
            assert expected in tip, f"Missing final tip for {command[:2]}"
            result = {"command": "co " + " ".join(command[:2]), "exit": exit_code,
                      "output": output, "tip": tip, "goal": goal, "expected": expected, "pipe_pass": True}
            if args.tip_model:
                from connectonion import llm_do
                try:
                    with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                        reply = llm_do(f"You just ran a shell command. Its full output was:\n\n{output}\n\n"
                                       f"Your goal: {goal} Reply with ONE shell command and nothing else.",
                                       model=args.tip_model)
                    result.update(model=args.tip_model, reply=reply.strip(), tip_pass=reply.strip() == expected)
                except Exception:
                    result.update(model=args.tip_model, tip_pass=False, error="Text-only model call failed; details withheld")
            results.append(result)
    args.output.write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"pipe_pass": sum(row["pipe_pass"] for row in results), "total": len(results),
                      "tip_pass": sum(row.get("tip_pass", False) for row in results) if args.tip_model else None,
                      "output": str(args.output)}))
    return 0 if all(row.get("tip_pass", True) for row in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
