"""A served task's `before` comes in two shapes, and the native turn must accept both.

Most stages carry `before` as {record: page text}. The tag-node stage (#3140) carries the tag page as one string, or ""
when the page is new. Until rc37 the native turn assumed the dict: every scheduled turn that reached a tag page crashed
in `_source_view` with "'str' object has no attribute 'values'", and the night wrote nothing from then on.

Invented data only.
"""
import json

from connectonion.rem import native, native_round
from connectonion.rem.config import read_config
from connectonion.rem.files import Notebook, write_json
from tests.unit.test_rem_night_shares import cursor_of, notebook  # noqa: F401
from tests.unit.test_rem_tag_round import people


def tag_node_task(root):
    """The tag-node task a real round serves after tagging, the shape the scheduled turn saves."""
    people(root, 3)
    cursor = cursor_of(root, [])
    directory = root / "task"
    directory.mkdir(exist_ok=True)
    while (task := native_round.prepare_task(root, cursor, read_config(root), directory)) is not None:
        if task["stage"] == "tag-node":
            return task, directory
        value = {"pages": [{"id": page, "tags": [{"tag": "student", "evidence": "Student in COMP9900"}]}
                           for page in task["task"]["ids"]],
                 "new_tags": [{"tag": "student", "label": "student", "kind": "role"}]}
        native_round.advance(root, cursor, {**task, "directory": str(directory)},
                             native_round.check_task(root, task, {"result": json.dumps(value)}))
    raise AssertionError("the round served no tag-node task")


def test_a_new_tag_page_task_carries_an_empty_string_before_and_is_saved(notebook):
    task, directory = tag_node_task(notebook)
    assert task["task"]["before"] == ""
    native._inputs(notebook, task["task"], directory, handler=task["handler"])
    assert native._source_view(notebook, task["task"], handler=task["handler"])


def test_an_existing_tag_page_task_carries_the_page_text_and_is_saved(notebook):
    task, directory = tag_node_task(notebook)
    page = "# Student\n\nStudents in COMP9900 [1].\n\n## Sources\n- [1] mail:invented-1\n"
    stage_task = {**task["task"], "before": page}
    inputs = native._inputs(notebook, stage_task, directory, handler=task["handler"])
    assert str(Notebook(notebook).path(stage_task["record"])) in {str(path) for path in inputs} or inputs
    assert native._source_view(notebook, stage_task, handler=task["handler"])


def test_recovering_an_accepted_tag_page_compares_the_one_page(notebook):
    task, directory = tag_node_task(notebook)
    record = task["task"]["record"]
    write_json(directory / "promotion.json", {"record": record, "sha256": "0" * 64})
    result = native._recovered_result(notebook, {"directory": str(directory), "task": {**task["task"], "before": "old"}})
    assert result["changed"] == [record]


def test_recovering_an_unchanged_tag_page_reports_no_change(notebook):
    import hashlib
    task, directory = tag_node_task(notebook)
    record, page = task["task"]["record"], "# Student\n\nStudents [1].\n"
    write_json(directory / "promotion.json", {"record": record, "sha256": hashlib.sha256(page.encode()).hexdigest()})
    result = native._recovered_result(notebook, {"directory": str(directory), "task": {**task["task"], "before": page}})
    assert result["changed"] == []
