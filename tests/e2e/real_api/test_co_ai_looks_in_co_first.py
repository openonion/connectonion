"""co ai reaches a service through its co command, found from --help, not through the browser.

LLM-Note: Opt-in (real_api). Runs a real `co ai` one-shot turn (a few cents of
credits) against the Linear workspace the key opens, from an empty directory.

Asked "What's open on my Linear board?" on 1.8.10, co ai ran `co --help`, saw
`co linear`, then spent 20-odd browser steps (72-248 s, $0.08-0.14) reading
linear.app instead of running one command. Nothing in its prompt said that a
service usually has a `co` command. With that rule it reads `co linear --help`
and answers from `co linear issues` in four calls.

The `co` on PATH must be this checkout's, or the agent finds an older co that
has no `co linear` and the browser is the right answer.

    pytest -m real_api tests/e2e/real_api/test_co_ai_looks_in_co_first.py -s
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest

from connectonion.environment import setting

pytestmark = [
    pytest.mark.real_api,
    pytest.mark.skipif(not setting("LINEAR_API_KEY"), reason="LINEAR_API_KEY not set (co env set LINEAR_API_KEY lin_api_... --secret)"),
    pytest.mark.skipif(not setting("OPENONION_API_KEY"), reason="co ai needs OPENONION_API_KEY (co init)"),
]


def test_a_linear_question_is_answered_with_co_linear(tmp_path):
    bin_dir = Path(sys.executable).parent
    env = {**os.environ, "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}", "NO_COLOR": "1", "COLUMNS": "120"}
    run = subprocess.run([str(bin_dir / "co"), "ai", "What's open on my Linear board?"],
                         cwd=tmp_path, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=600)
    shell = [line for line in run.stdout.splitlines() if "⚡ bash: " in line]
    print("\n".join(shell))

    assert run.returncode == 0, run.stdout[-2000:]
    assert any("bash: co linear" in line for line in shell), shell
    assert not any("bash: co browser" in line for line in shell), shell
