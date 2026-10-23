"""Recorded input is observable; selection and model inspection are different states."""
import json

import pytest

from test_rem_partial_reader import partial_reader


def test_failed_selected_source_is_not_presented_as_read():
    result = partial_reader(run_override={"items_by_source":{"codex":12}})
    text = json.dumps(result["band"])
    assert "12 recorded inputs" in text and "Read 12 items" not in text
    assert "Source coverage" in text and "not proof of model inspection" in text
    rows = {r["name"]:r for r in result["input"]["sources"]}
    assert rows["gmail"]["selected"] == rows["codex"]["selected"] == 1
    assert rows["gmail"]["items"] == 0 and rows["gmail"]["failures"] == 1
    assert rows["codex"]["items"] == 12 and rows["codex"]["failures"] == 0


def test_input_before_runner_failure_does_not_become_inspection():
    result = partial_reader(run_override={"outcome":"failed", "stage":"maintain", "items_by_source":{"codex":12}})
    text = json.dumps(result["item"])
    assert "12 recorded inputs" in text and '12 read' not in text
    assert "PRIVATE_PAYLOAD" not in text


@pytest.mark.parametrize("items", [None, "12", -1, 1.5, True])
def test_missing_or_invalid_counts_are_unknown_not_zero(items):
    result = partial_reader(run_override={"items":items, "items_by_source":{}})
    assert result["input"]["unknownItems"] == 1
    assert "Input count not recorded" in json.dumps(result["band"])
    assert "Input count not recorded" in json.dumps(result["item"])


@pytest.mark.parametrize("breakdown", [None, [], {"codex":7}, {"codex":"12"}, {"codex":-1}])
def test_unverifiable_source_breakdown_does_not_attribute_all_inputs(breakdown):
    result = partial_reader(run_override={"items_by_source":breakdown})
    assert result["input"]["items"] == 12 and result["input"]["unknownSources"] == 1
    assert all(r["unknown"] == 1 for r in result["input"]["sources"])
    assert "Per-source counts unavailable" in json.dumps(result["band"])


def test_repeated_run_inputs_are_totals_not_unique_memories_or_inspection():
    other = {"id":"run_again", "started_at":"2026-10-23T07:03:00Z", "outcome":"completed",
             "items":12, "items_by_source":{"codex":12}, "sources":["codex"]}
    result = partial_reader(run_override={"items_by_source":{"codex":12}}, extra_runs=[other])
    assert result["input"]["items"] == 24
    assert "Counts total per-run inputs; repeats may occur." in json.dumps(result["band"])


def test_legacy_missing_counts_stay_unknown_when_other_run_is_measured():
    other = {"started_at":"2026-10-23T07:03:00Z", "outcome":"completed", "sources":["gmail"]}
    result = partial_reader(run_override={"items_by_source":{"codex":12}}, extra_runs=[other])
    assert result["input"]["items"] == 12 and result["input"]["unknownItems"] == 1
    assert "12 recorded inputs + unknown" in json.dumps(result["band"])


def test_zero_inputs_are_recorded_zero_without_claiming_source_caught_up():
    result = partial_reader(run_override={"items":0, "items_by_source":{}})
    assert result["input"]["unknownItems"] == 0
    text = json.dumps(result["band"])
    assert "0 recorded inputs" in text and "caught up" not in text


def test_source_selection_and_failure_counts_deduplicate_within_each_run():
    result = partial_reader(run_override={"sources":["gmail", {"kind":"gmail"}, "codex"],
        "items_by_source":{"codex":12}, "source_failures":[{"source":"gmail"}, {"source":"gmail"}],
        "failed_source":"gmail"})
    row = next(r for r in result["input"]["sources"] if r["name"] == "gmail")
    assert row["selected"] == row["failures"] == 1


def test_coverage_labels_are_translated():
    result = partial_reader(language="zh", run_override={"items_by_source":{"codex":12}})
    text = json.dumps(result["band"], ensure_ascii=False)
    assert "来源覆盖" in text and "不代表模型已检查" in text
    assert "recorded inputs" not in text


def test_missing_selection_is_not_claimed_as_explicit_zero_selections():
    result = partial_reader(run_override={"sources":None, "items_by_source":{"codex":12}})
    row = next(r for r in result["input"]["sources"] if r["name"] == "codex")
    assert row["selectionUnknown"] == result["input"]["unknownSelection"] == 1
    assert "Source selection unavailable" in json.dumps(result["band"])


def test_explicit_empty_source_selection_does_not_become_missing_metadata():
    result = partial_reader(run_override={"sources":[], "source_failures":[], "items":0, "items_by_source":{}})
    assert result["input"]["unknownSelection"] == 0
    assert "No source rows recorded" in json.dumps(result["band"])


def test_overflowing_counter_totals_are_not_reported_as_precise_numbers():
    other = {"started_at":"2026-10-23T07:03:00Z", "items":9007199254740991, "sources":["codex"]}
    result = partial_reader(extra_runs=[other])
    assert result["input"]["unknownItems"] == 1
    assert "12 recorded inputs + unknown" in json.dumps(result["band"])


def test_daily_parent_placeholder_is_not_claimed_as_a_measured_zero():
    result = partial_reader(run_override={"phase":"daily-investigation", "items":0, "sources":[],
        "source_failures":[], "pages":[{"page":"projects/current.md", "outcome":"accepted"}]})
    assert result["input"]["unknownItems"] == result["input"]["unknownSelection"] == 1
    assert "Input count not recorded" in json.dumps(result["band"])


@pytest.mark.parametrize("source", ["constructor", "toString", "__proto__", "<img onerror=bad>"])
def test_source_names_remain_literal_table_text(source):
    result = partial_reader(run_override={"sources":[source], "items":0, "items_by_source":{}, "source_failures":[]})
    assert '\"scope\": \"row\", \"text\": ' + json.dumps(source) in json.dumps(result["band"])


@pytest.mark.parametrize("word", ["read", "gathered"])
def test_legacy_and_current_gathering_counts_preserve_queue_compatibility(word):
    from connectonion.rem.queue import _material_read
    assert _material_read([f"gmail: 2 bodies {word}, 1 attachments {word}"]) == 3
