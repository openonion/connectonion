"""`co rem person` is the reader's 不是人 / 是人 on the command line (#3355): an agent can classify a contact."""
import json

from typer.testing import CliRunner

from connectonion.cli.main import app
from connectonion.rem.threads import person_marks

runner = CliRunner()


def _run(root, *args):
    return runner.invoke(app, ["rem", "--root", str(root), "--json", "person", *args])


def test_a_wechat_handle_can_be_marked_not_a_person_and_reset(tmp_path):
    root = tmp_path / "rem"
    root.mkdir()
    result = _run(root, "wxid_shop123", "--not-person")
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["data"]["person"] is False
    assert person_marks(root).get("wxid_shop123") == "not-person"
    _run(root, "wxid_shop123", "--reset")
    assert "wxid_shop123" not in person_marks(root)


def test_exactly_one_choice_and_one_handle_never_a_pattern(tmp_path):
    root = tmp_path / "rem"
    root.mkdir()
    assert _run(root, "wxid_a", "--person", "--not-person").exit_code != 0
    assert _run(root, "wxid_a").exit_code != 0
    assert _run(root, "*@example.com", "--not-person").exit_code != 0
    assert person_marks(root) == {}
