"""The export and draft stages share the same full-record character budget."""

import json

import pytest

from connectonion.rem.files import RemError
from connectonion.rem.imported_evidence import MAX_EVIDENCE_CHARS, evidence_material
from connectonion.useful_tools.adapter import make_record


def record(text="", **kwargs):
    return make_record("jira", "example.test", "EX-1", "issue", text=text, **kwargs)


def test_non_ascii_and_nested_metadata_are_kept_without_ascii_expansion():
    row = record("中" * 15_000, extensions={"history": [{"from": "待办", "to": "完成"}]})
    assert len(json.dumps([row])) > MAX_EVIDENCE_CHARS
    material = evidence_material([row])
    assert json.loads(material[0]) == row
    assert "中" in material[0]


def test_previously_exportable_nested_history_is_rejected_consistently():
    row = record(extensions={"history": [{"field": "status", "from": "Open", "to": "In Progress"}
                                        for _ in range(30)]})
    row["text"] = "x" * (79_950 - len(json.dumps([row])))
    assert len(json.dumps([row])) == 79_950
    with pytest.raises(RemError, match="80,000"):
        evidence_material([row])


def test_budget_boundary_includes_every_record():
    rows = [record(), record()]
    size = sum(len(json.dumps(row, ensure_ascii=False, indent=2)) for row in rows)
    rows[0]["text"] = "x" * (MAX_EVIDENCE_CHARS - size)
    assert sum(map(len, evidence_material(rows))) == MAX_EVIDENCE_CHARS
    rows[1]["text"] = "x"
    with pytest.raises(RemError, match="too long"):
        evidence_material(rows)


@pytest.mark.parametrize("count", [0, 21])
def test_record_count_is_bounded(count):
    with pytest.raises(RemError, match="1–20"):
        evidence_material([record()] * count)
