"""An init inventory must be useful without claiming the provider's full total."""

import json
import os
from datetime import datetime, timedelta, timezone

import pytest

from connectonion.wiki.config import prepare
from connectonion.wiki.map import build_map
from connectonion.wiki.source_inventory import SourceInventory


def test_inventory_is_private_bounded_and_replaced_on_rerun(tmp_path):
    inventory = SourceInventory(tmp_path)
    row = {"id": "mail-1", "date": "2026-09-26", "from": "a@example.org",
           "to": ["me@example.org"], "subject": "Hello", "bodyPreview": "private preview",
           "body": "private body", "authorization": "secret"}
    inventory.mail("gmail", row)
    inventory.window("gmail", "2026-09-19", "2026-09-26", 200, 200)
    inventory.session("codex", tmp_path / "session.jsonl", datetime.now(timezone.utc), "/repo")
    report = {"started": "2026-09-26T00:00:00+00:00", "days": 7, "skills": {"skills": [{}]},
              "coverage": [], "errors": []}
    details = inventory.save(report)
    records = tmp_path / details["records"]
    content = records.read_text()
    assert "private preview" not in content and "private body" not in content
    assert "secret" not in content
    assert details["mail_observed"] == 1 and details["capped_mail_windows"] == 1
    assert details["mailbox_total"] == "unknown"
    assert "possibly truncated" in (tmp_path / details["summary"]).read_text()
    assert os.stat(records).st_mode & 0o777 == 0o600
    inventory.save(report)
    assert len(records.read_text().splitlines()) == 2
    assert json.loads(content.splitlines()[0])["id"] == "mail-1"


def test_init_captures_mail_metadata_and_progress_without_model(tmp_path):
    prepare(tmp_path)
    skills = tmp_path / "empty-skills"
    skills.mkdir()
    events = []

    class Mail:
        def my_addresses(self):
            return {"me@example.org"}

        def list_between(self, start, end, limit):
            return [{"id": "m1", "date": end, "from": "a@example.org",
                     "to": ["me@example.org"], "subject": "Project", "body": "not stored"}]

    result = build_map(tmp_path, {}, {"gmail": Mail()}, days=1, skill_directories=[skills],
                       capture_sources=True, progress=events.append)
    assert result["phase"] == "mapped"
    assert result["source_inventory"]["mail_observed"] == 1
    assert events[0].startswith("Skills:")
    assert any(event.startswith("gmail: scanning") for event in events)
    assert events[-1].startswith("Map saved:")
    assert "not stored" not in (tmp_path / ".state/source-inventory.jsonl").read_text()
    again = build_map(tmp_path, {}, {"gmail": Mail()}, days=1, skill_directories=[skills],
                      capture_sources=True)
    assert again["source_inventory"]["mail_observed"] == 1
    assert len((tmp_path / ".state/source-inventory.jsonl").read_text().splitlines()) == 1


@pytest.mark.parametrize("cap_end", ["oldest", "newest"])
def test_init_enumerates_all_90_day_mail_past_provider_page_cap(tmp_path, cap_end):
    prepare(tmp_path)
    skills = tmp_path / "empty-skills"
    skills.mkdir()
    first = datetime.now(timezone.utc) - timedelta(hours=1)
    messages = [{"id": str(i), "date": (first + timedelta(seconds=i)).isoformat(),
                 "from": "a@example.org", "to": ["me@example.org"], "subject": "Project"}
                for i in range(250)]

    class Mail:
        def my_addresses(self):
            return {"me@example.org"}

        def list_between(self, start, end, limit):
            hits = [row for row in messages if start <= row["date"] < end]
            return (hits[:limit] if cap_end == "oldest" else hits[-limit:])

    result = build_map(tmp_path, {}, {"gmail": Mail()}, days=90, skill_directories=[skills],
                       capture_sources=True)
    assert result["phase"] == "mapped"
    assert result["source_inventory"]["mail_observed"] == 250
    assert result["source_inventory"]["capped_mail_windows"] == 0
    assert result["source_inventory"]["split_mail_windows"] == 1
    assert len((tmp_path / ".state/source-inventory.jsonl").read_text().splitlines()) == 250
    assert next(row for row in result["people"] if row.get("address") == "a@example.org")["mails"] == 250


def test_unenumerable_dense_mail_window_is_partial_not_complete(tmp_path):
    prepare(tmp_path)
    skills = tmp_path / "empty-skills"
    skills.mkdir()

    class Mail:
        def my_addresses(self):
            return {"me@example.org"}

        def list_between(self, start, end, limit):
            # A provider that always reports a full page, even at one second.
            return [{"id": str(i), "date": start, "from": "a@example.org"}
                    for i in range(limit)]

    result = build_map(tmp_path, {}, {"gmail": Mail()}, days=1, skill_directories=[skills],
                       capture_sources=True)
    assert result["phase"] == "partial"
    assert result["errors"] == [{"source": "gmail", "stage": "metadata", "error": "WikiError"}]
    assert result["source_inventory"]["mail_observed"] == 0
