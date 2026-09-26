"""The first pass stores mail once and investigation can read it locally."""

import json
import os
from datetime import datetime, timedelta, timezone

from connectonion.wiki.config import prepare
from connectonion.wiki.investigate import gather
from connectonion.wiki.mail_archive import archive_init, person_index_path, project_index_path
from connectonion.wiki.map import build_map


def test_init_archive_is_private_resumable_and_people_read_it_without_listing(tmp_path):
    prepare(tmp_path)
    skills = tmp_path / "source-skills"
    skills.mkdir()
    when = (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat()
    rows = [{"id": "shared", "date": when, "from": "me@example.org",
             "to": ["a@example.org", "b@example.org"], "cc": [], "subject": "Plan"},
            {"id": "reply", "date": (datetime.fromisoformat(when) + timedelta(minutes=1)).isoformat(),
             "from": "a@example.org",
             "to": ["me@example.org"], "cc": [], "subject": "Re: Plan"}]

    class Mail:
        reads = 0

        def my_addresses(self):
            return {"me@example.org"}

        def list_between(self, start, end, limit):
            return [row for row in rows if start <= row["date"] < end]

        def get_email_body(self, message_id):
            self.reads += 1
            return f"--- Email Body ---\nbody {message_id}"

        def list_with(self, address, start, end):
            raise AssertionError("A fresh init archive should cover existing mail")

    mail = Mail()
    report = build_map(tmp_path, {}, {"gmail": mail}, days=1, skill_directories=[skills],
                       capture_sources=True)
    archive = archive_init(tmp_path, report, {"gmail": mail})
    assert archive["phase"] == "complete" and archive["saved"] == 2
    assert mail.reads == 2
    again = archive_init(tmp_path, report, {"gmail": mail})
    assert again["reused"] == 2 and mail.reads == 2
    by_address = {row.get("address"): row["record"] for row in report["people"]}
    a, b = by_address["a@example.org"], by_address["b@example.org"]
    assert len(person_index_path(tmp_path, a).read_text().splitlines()) == 2
    assert len(person_index_path(tmp_path, b).read_text().splitlines()) == 1
    stored = list((tmp_path / ".state/mail/messages/gmail").glob("*.json"))
    assert len(stored) == 2  # shared message is indexed twice, stored once
    assert all(os.stat(path).st_mode & 0o777 == 0o600 for path in stored)
    assert "body shared" not in (tmp_path / a).read_text()
    # Map metadata is persisted by the CLI after archiving; mimic that handoff.
    from connectonion.wiki.files import state_path, write_json
    write_json(state_path(tmp_path, "map.json"), {**report, "mail_archive": archive})
    items, coverage = gather("A", ["a@example.org"], days=1, clients={}, subscriptions={},
                             archive_root=tmp_path, record=a)
    assert [item["text"] for item in items] == ["--- Email Body ---\nbody shared",
                                                 "--- Email Body ---\nbody reply"]
    assert any("loaded from private init archive" in note for note in coverage)
    class DeltaMail:
        calls = []
        def my_addresses(self): return {"me@example.org"}
        def list_with(self, address, start, end):
            self.calls.append((address, start, end))
            return []
    delta = DeltaMail()
    gather("A", ["a@example.org"], days=1, clients={"gmail": delta}, subscriptions={},
           archive_root=tmp_path, record=a)
    assert len(delta.calls) == 1
    assert delta.calls[0][1] >= archive["range_end"]


def test_init_archive_builds_project_source_file(tmp_path, monkeypatch):
    wiki = tmp_path / "notebook"
    prepare(wiki)
    skills = tmp_path / "source-skills"
    skills.mkdir()
    sessions = tmp_path / "sessions"
    sessions.mkdir()
    source = sessions / "rollout-one.jsonl"
    source.write_text(json.dumps({"type": "session_meta", "payload": {"id": "one", "cwd": "/repo/project",
                                                                     "originator": "codex_cli_rs"}}) + "\n")
    subscription = {"codex": {"kind": "codex", "root": str(sessions), "enabled": True}}
    def scan(subscriptions, days, root, on_session=None):
        if on_session:
            on_session("codex", source, datetime.now(timezone.utc), "/repo/project")
        return [{"path": "/repo/project", "repo": "/repo/project", "origin": "",
                 "first": "2026-09-26", "last": "2026-09-26", "sessions": 1}]
    monkeypatch.setattr("connectonion.wiki.map.scan_projects", scan)
    report = build_map(wiki, subscription, {}, days=1, skill_directories=[skills],
                       capture_sources=True)
    archive = archive_init(wiki, report, {})
    assert archive["project_indexes"] == 1
    index = project_index_path(wiki, report["projects"][0]["record"])
    assert json.loads(index.read_text().splitlines()[0])["path"] == str(source)


def test_failed_body_fetch_resumes_without_refetching_successful_mail(tmp_path):
    prepare(tmp_path)
    skills = tmp_path / "source-skills"
    skills.mkdir()
    when = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()

    class Mail:
        calls = []
        fail_once = True
        def my_addresses(self): return {"me@example.org"}
        def list_between(self, start, end, limit):
            return [{"id": item, "date": when, "from": "a@example.org", "to": ["me@example.org"]}
                    for item in ("one", "two")] if start <= when < end else []
        def get_email_body(self, message_id):
            self.calls.append(message_id)
            if message_id == "two" and self.fail_once:
                self.fail_once = False
                raise TimeoutError("temporary")
            return f"body {message_id}"

    mail = Mail()
    report = build_map(tmp_path, {}, {"gmail": mail}, days=1, skill_directories=[skills],
                       capture_sources=True)
    first = archive_init(tmp_path, report, {"gmail": mail})
    assert first["phase"] == "partial" and (first["saved"], first["failed"]) == (1, 1)
    second = archive_init(tmp_path, report, {"gmail": mail})
    assert second["phase"] == "complete" and (second["reused"], second["saved"]) == (1, 1)
    assert mail.calls == ["one", "two", "two"]
