"""The delegation prompt describes hosted policy and declined outcomes."""

from pathlib import Path


def test_codex_prompt_explains_hosted_modes_and_declined_results():
    prompt = Path("connectonion/cli/co_ai/prompts/tools/codex.md").read_text()
    assert "workspace-write" in prompt
    assert "no approval prompts" in prompt
    assert "operator" in prompt
    assert "non-admin" in prompt
    assert "no approval UI" in prompt
    assert "status" in prompt and "blocked" in prompt
    assert "which actions were declined and why" in prompt
    assert "never say the work was done" in prompt
