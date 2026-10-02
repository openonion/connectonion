"""The editorial CI gate distinguishes unavailable judgment from a bad post."""

import importlib.util
import sys
from pathlib import Path

from connectonion.core.exceptions import InsufficientCreditsError


def _gate():
    path = Path(__file__).resolve().parents[2] / ".github/scripts/check_blog_story.py"
    spec = importlib.util.spec_from_file_location("check_blog_story", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_exhausted_blog_model_warns_once_without_judging_the_post(monkeypatch, capsys):
    gate = _gate()
    calls = []

    def unavailable(*args, **kwargs):
        calls.append((args, kwargs))
        original = RuntimeError("402")
        original.body = {"detail": {"balance": 0}}
        raise InsufficientCreditsError(original)

    monkeypatch.setattr(gate, "llm_do", unavailable)
    assert gate._judge("A story with a problem and a turn") is None
    assert len(calls) == 1
    warning = capsys.readouterr().out
    assert "::warning::" in warning and "human read" in warning
    assert "Account:" not in warning


def test_a_real_not_story_verdict_still_fails(monkeypatch, tmp_path, capsys):
    gate = _gate()
    post = tmp_path / "post.md"
    post.write_text("A list of features.")
    monkeypatch.setattr(gate, "llm_do", lambda *a, **kw: "NOT_STORY: Give it a turn.")
    monkeypatch.setattr(sys, "argv", ["check_blog_story.py", str(post)])
    assert gate.main() == 1
    assert "::error::" in capsys.readouterr().out
