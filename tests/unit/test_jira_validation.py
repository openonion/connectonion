"""Live acceptance must compare the existing namespaced source envelope correctly."""

from copy import deepcopy

import pytest

from connectonion.useful_tools.adapter import jira_issues_to_records
from scripts.validation.jira_live_readonly import source_titles_match


@pytest.mark.parametrize("change", [None, "title", "external_id", "duplicate"])
def test_live_comparison_accepts_only_matching_source_versions(change):
    issues = [{"key": "ALPHA-1", "fields": {"summary": "Literal :warning: [draft]"}}]
    records = jira_issues_to_records(issues, "https://fixture.atlassian.net").records
    assert records[0]["id"] != records[0]["external_id"]
    if change == "duplicate":
        records.append(deepcopy(records[0]))
    elif change:
        records[0][change] = "mismatch"
    assert source_titles_match(records, issues) is (change is None)
