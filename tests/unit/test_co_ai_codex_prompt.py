"""The delegation prompt describes hosted policy and declined outcomes."""

from pathlib import Path

import connectonion

# The installed package's own file, not a path relative to wherever pytest runs:
# the suite's isolation fixtures may change the working directory.
CODEX_PROMPT = Path(connectonion.__file__).parent / "cli/co_ai/prompts/tools/codex.md"


def test_codex_prompt_explains_hosted_modes_and_declined_results():
    prompt = CODEX_PROMPT.read_text(encoding="utf-8")
    assert "workspace-write" in prompt
    assert "no approval prompts" in prompt
    assert "operator" in prompt
    assert "non-admin" in prompt
    assert "no approval UI" in prompt
    assert "status" in prompt and "blocked" in prompt
    assert "which actions were declined and why" in prompt
    assert "never say the work was done" in prompt
