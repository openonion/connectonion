"""`co rem investigate PAGE` and its steps: --enrich, --quick, --rewrite and its draft, --undo (#3105).

The model is replaced at the module boundary (investigate.investigate and
muse.enrich); everything between the parser and the page is the real CLI.
"""

import json

from typer.testing import CliRunner

from connectonion.cli.main import app
from connectonion.rem import page_versions
from connectonion.rem.config import prepare
from connectonion.rem.files import Notebook

PAGE = "people/avery.md"
BEFORE = ("# Avery Lin\n\n## Who they are\n- Avery leads design. [1]\n\n## Sources\n- [1] gmail:aaaaaaaaaaaa\n\n"
          "Investigation: investigated 2026-09-02 (gmail)\n")
APPENDED = BEFORE.replace("- Avery leads design. [1]", "- Avery leads design. [1]\n- Avery joined the board. [2]")


def invoke(root, *args):
    return CliRunner().invoke(app, ["rem", "--root", str(root), "--json", *args])


def _notebook(tmp_path, monkeypatch, calls):
    root = tmp_path / "rem"
    prepare(root)
    Notebook(root).write(PAGE, BEFORE)

    def investigate(root, record, *args, mode="", **kwargs):
        calls.append(("investigate", mode))
        Notebook(root).write(record, APPENDED if mode != "rewrite" else "# Avery Lin\n\nRewritten whole.\n")
        return {"changed": [record], "usage": None, "mode": "write" if mode == "rewrite" else "append"}

    def enrich(root, record, *, runner=None, stage_progress=None):
        calls.append(("enrich", ""))
        return {"record": record, "changed": [], "page_chars": [1, 1], "report": "- open | a lead", "usage": None}
    monkeypatch.setattr("connectonion.rem.investigate.investigate", investigate)
    monkeypatch.setattr("connectonion.rem.muse.enrich", enrich)
    return root


def test_page_alone_appends_without_the_web_step(tmp_path, monkeypatch):
    calls = []
    root = _notebook(tmp_path, monkeypatch, calls)
    for extra in ([], ["--quick"]):
        calls.clear()
        result = invoke(root, "investigate", PAGE, *extra)
        assert result.exit_code == 0, result.output
        assert calls == [("investigate", "")]


def test_enrich_runs_after_the_append_and_the_old_command_says_it_moved(tmp_path, monkeypatch):
    calls = []
    root = _notebook(tmp_path, monkeypatch, calls)
    result = invoke(root, "investigate", PAGE, "--enrich")
    assert result.exit_code == 0, result.output
    assert calls == [("investigate", ""), ("enrich", "")]
    assert json.loads(result.stdout)["data"]["enrich"]["leads"] == "- open | a lead"
    calls.clear()
    moved = CliRunner().invoke(app, ["rem", "--root", str(root), "enrich", PAGE])
    assert moved.exit_code == 0, moved.output
    assert calls == [("investigate", ""), ("enrich", "")]
    assert "co rem investigate PAGE --enrich" in moved.output


def test_enrich_still_runs_when_there_is_nothing_new_to_append(tmp_path, monkeypatch):
    from connectonion.rem.investigate import NothingNew
    calls = []
    root = _notebook(tmp_path, monkeypatch, calls)

    def nothing(root, record, *args, mode="", **kwargs):
        calls.append(("investigate", mode))
        raise NothingNew("Nothing new for Avery Lin since 2026-09-02.")
    monkeypatch.setattr("connectonion.rem.investigate.investigate", nothing)
    result = invoke(root, "investigate", PAGE, "--enrich")
    assert result.exit_code == 0, result.output
    assert calls == [("investigate", ""), ("enrich", "")]


def test_a_rewrite_waits_as_a_draft_until_accepted_and_can_be_undone(tmp_path, monkeypatch):
    calls = []
    root = _notebook(tmp_path, monkeypatch, calls)
    result = invoke(root, "investigate", PAGE, "--rewrite")
    assert result.exit_code == 0, result.output
    assert calls == [("investigate", "rewrite")]
    assert Notebook(root).read(PAGE) == BEFORE
    assert page_versions.waiting_rewrite(root, PAGE)
    accepted = invoke(root, "investigate", PAGE, "--accept-rewrite")
    assert accepted.exit_code == 0, accepted.output
    assert Notebook(root).read(PAGE).startswith("# Avery Lin\n\nRewritten whole.")
    undone = invoke(root, "investigate", PAGE, "--undo")
    assert undone.exit_code == 0, undone.output
    assert Notebook(root).read(PAGE) == BEFORE


def test_an_append_can_be_undone_and_a_discarded_draft_is_gone(tmp_path, monkeypatch):
    calls = []
    root = _notebook(tmp_path, monkeypatch, calls)
    assert invoke(root, "investigate", PAGE).exit_code == 0
    assert Notebook(root).read(PAGE) == APPENDED
    assert invoke(root, "investigate", PAGE, "--undo").exit_code == 0
    assert Notebook(root).read(PAGE) == BEFORE
    assert invoke(root, "investigate", PAGE, "--rewrite").exit_code == 0
    assert invoke(root, "investigate", PAGE, "--discard-rewrite").exit_code == 0
    assert page_versions.waiting_rewrite(root, PAGE) is None
    refused = invoke(root, "investigate", PAGE, "--accept-rewrite")
    assert refused.exit_code != 0 and "No rewrite draft" in refused.output


def test_the_page_steps_need_one_page(tmp_path, monkeypatch):
    calls = []
    root = _notebook(tmp_path, monkeypatch, calls)
    for flag in ("--enrich", "--rewrite", "--undo", "--accept-rewrite"):
        result = invoke(root, "investigate", "people", flag)
        assert result.exit_code != 0 and "one page" in result.output, (flag, result.output)
    assert calls == []
