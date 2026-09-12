"""blog-gate's story check must not read a provider outage as a bad post.

The check failed a post with a Gemini 503 — "This model is currently
experiencing high demand" — minutes after the identical check passed on the
same text locally. Nothing about the writing had changed; the model was busy.

A gate that goes red for reasons the author cannot act on is a gate the team
learns to ignore, and then it is not protecting anything. The rule this repo
already keeps elsewhere: tell "I could not check" from "this is broken", and
let the first one through with a notice.
"""

import importlib.util
import sys
from pathlib import Path

import pytest

from connectonion.core.exceptions import ProviderServiceError

SCRIPT = Path(__file__).resolve().parents[2] / ".github" / "scripts" / "check_blog_story.py"


def _overload() -> Exception:
    """What the provider actually raised: a 503 with a body, wrapped by
    ProviderServiceError, which reads status_code and response off it."""
    error = RuntimeError(
        '503 - {"error": {"code": 503, "message": "This model is currently '
        'experiencing high demand.", "status": "UNAVAILABLE"}}'
    )
    error.status_code = 503
    return error


@pytest.fixture
def gate(monkeypatch):
    """The script, loaded as a module, with its model call replaceable."""
    spec = importlib.util.spec_from_file_location("check_blog_story", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, "check_blog_story", module)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module.time, "sleep", lambda *_: None)   # no real backoff in tests
    return module


@pytest.fixture
def post(tmp_path):
    path = tmp_path / "2026-01-01-a-post.md"
    path.write_text("# A post\n\nSomething happened, then something turned.\n", encoding="utf-8")
    return path


def test_a_story_passes(gate, post, monkeypatch):
    monkeypatch.setattr(gate, "llm_do", lambda *a, **k: "STORY: it has an arc")
    monkeypatch.setattr(gate.sys, "argv", ["check_blog_story.py", str(post)])

    assert gate.main() == 0


def test_a_changelog_wearing_prose_fails(gate, post, monkeypatch):
    monkeypatch.setattr(gate, "llm_do", lambda *a, **k: "NOT_STORY: it lists changes; tell what broke")
    monkeypatch.setattr(gate.sys, "argv", ["check_blog_story.py", str(post)])

    assert gate.main() == 1


def test_an_unreachable_model_does_not_fail_the_post(gate, post, monkeypatch, capsys):
    """The 503 case. Retried, then reported as unchecked — not as bad."""
    calls = []

    def overloaded(*args, **kwargs):
        calls.append(1)
        raise ProviderServiceError(_overload())

    monkeypatch.setattr(gate, "llm_do", overloaded)
    monkeypatch.setattr(gate.sys, "argv", ["check_blog_story.py", str(post)])

    assert gate.main() == 0, "a provider outage must not read as a failing post"
    assert len(calls) == 3, "the outage should be retried before giving up"
    out = capsys.readouterr().out
    assert "::warning::" in out
    assert "did not run" in out
    assert "::error::" not in out, "an unchecked post must not look like a rejected one"


def test_a_transient_outage_still_gets_judged(gate, post, monkeypatch):
    """One 503 then an answer: the verdict is the answer, not the outage."""
    answers = iter([
        ProviderServiceError(_overload()),
        "NOT_STORY: it is a commit list",
    ])

    def flaky(*args, **kwargs):
        result = next(answers)
        if isinstance(result, Exception):
            raise result
        return result

    monkeypatch.setattr(gate, "llm_do", flaky)
    monkeypatch.setattr(gate.sys, "argv", ["check_blog_story.py", str(post)])

    assert gate.main() == 1


def test_a_post_deleted_in_the_pr_is_skipped(gate, tmp_path, monkeypatch):
    monkeypatch.setattr(gate, "llm_do", lambda *a, **k: pytest.fail("should not judge a missing file"))
    monkeypatch.setattr(gate.sys, "argv", ["check_blog_story.py", str(tmp_path / "gone.md")])

    assert gate.main() == 0
