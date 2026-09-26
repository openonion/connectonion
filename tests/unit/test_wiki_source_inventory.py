"""An init inventory must be useful without claiming the provider's full total."""

import json
import os
from datetime import datetime, timezone

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
