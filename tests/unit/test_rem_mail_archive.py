"""The first pass stores mail once and investigation can read it locally."""

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

from connectonion.rem.config import prepare
from connectonion.rem.investigate import gather
from connectonion.rem.mail_archive import archive_init, person_index_path, project_index_path
from connectonion.rem.map import build_map


def test_material_keeps_named_corecipients_separate_from_the_reply_author():
    from connectonion.rem.mail_archive import _material_item
    from connectonion.rem.runner import readable_material
    snapshot = {"provider": "outlook", "id": "group-reply", "from": "Mentor <mentor@school.example>",
                "to": ["Me <me@example.org>", "Alex Chen <a@school.example>"],
                "cc": ["Guest <guest@school.example>"], "date": "2026-09-11T12:00:00Z",
                "body": "--- Email Body ---\nIt is not too late to submit.\nMentor", "subject": "Re: project"}
    item = _material_item(snapshot, {"me@example.org"})
    assert item["role"] == "other" and item["speaker"] == snapshot["from"]
    assert item["participants"] == {key: snapshot[key] for key in ("from", "to", "cc")}
    supplied = readable_material([item])
    assert 'Alex Chen <a@school.example>' in supplied and 'Guest <guest@school.example>' in supplied
    assert item["text"] == snapshot["body"]


def test_person_archive_keeps_exact_thread_replies_after_cc_member_is_dropped(tmp_path):
    from connectonion.rem.files import state_path, write_json
    from connectonion.rem.mail_archive import message_path, person_material
    from connectonion.rem.fact_extract import extract
    prepare(tmp_path)
    record = "people/member.md"
    rows = [
        {"source": "outlook", "id": "request", "thread": "scope", "from": "lead@school.example",
         "to": ["me@example.org"], "cc": ["member@school.example"], "date": "2026-10-01T00:00:00Z"},
        {"source": "outlook", "id": "approval", "thread": "scope", "from": "me@example.org",
         "to": ["lead@school.example"], "cc": [], "date": "2026-10-02T00:00:00Z"},
        {"source": "outlook", "id": "other-team", "thread": "other", "from": "lead@school.example",
         "to": ["me@example.org"], "cc": [], "date": "2026-10-02T01:00:00Z"},
        {"source": "gmail", "id": "collision", "thread": "scope", "from": "lead@school.example",
         "to": ["me@example.org"], "cc": [], "date": "2026-10-02T02:00:00Z"},
        {"source": "outlook", "id": "unthreaded", "thread": "", "from": "lead@school.example",
         "to": ["me@example.org"], "cc": [], "date": "2026-10-02T03:00:00Z"},
    ]
    write_json(state_path(tmp_path, "mail/archive.json"), {
        "phase": "complete", "providers": ["outlook", "gmail"], "owner_addresses": ["me@example.org"],
        "range_start": "2026-10-01T00:00:00+00:00", "range_end": "2026-10-03T00:00:00+00:00"})
    state_path(tmp_path, "source-inventory.jsonl").write_text("".join(
        json.dumps({"type": "mail", "subject": "Scope approval", **r}) + "\n" for r in rows))
    for row in rows:
        write_json(message_path(tmp_path, row["source"], row["id"]), {
            **row, "provider": row["source"], "subject": "Scope approval",
            "body": "Approved with additions." if row["id"] == "approval" else "Please approve."})
    index = person_index_path(tmp_path, record)
    index.parent.mkdir(parents=True, exist_ok=True)
    index.write_text(json.dumps({"provider": "outlook", "id": "request", "roles": ["cc"],
        "message": str(message_path(tmp_path, "outlook", "request").relative_to(tmp_path))}) + "\n")
    material, _, _ = person_material(tmp_path, record)
    items = material["outlook"]
    assert len(items) == 2 and not material["gmail"]
    request, approval = items
    assert "relationship_scope" not in request
    assert "not addressed to this person" in approval["relationship_scope"]
    assert approval["role"] == "user" and approval["text"] == "Approved with additions."
    facts = extract([i for i in items if not i.get("relationship_scope")], ["member@school.example"])
    assert all(r["value"] != "2026-10-02" for r in facts if r["field"] == "Last contact")


def test_init_archive_is_private_resumable_and_people_read_it_without_listing(tmp_path):
    prepare(tmp_path)
    skills = tmp_path / "source-skills"
    skills.mkdir()
    when = (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat()
    rows = [{"id": "shared", "date": when, "from": "me@example.org",
             "to": ["a@example.org", "b@example.org"], "cc": [], "subject": "Plan"},
            {"id": "reply", "date": (datetime.fromisoformat(when) + timedelta(minutes=1)).isoformat(),
             "from": "a@example.org",
             "to": ["me@example.org"], "cc": [], "subject": "Re: Plan"},
            # b answers too: someone who only ever got one mail has no page to index (#2057).
            {"id": "b-reply", "date": (datetime.fromisoformat(when) + timedelta(minutes=2)).isoformat(),
             "from": "b@example.org",
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
    assert archive["phase"] == "complete" and archive["saved"] == 3
    assert mail.reads == 3
    again = archive_init(tmp_path, report, {"gmail": mail})
    assert again["reused"] == 3 and mail.reads == 3
    by_address = {row.get("address"): row["record"] for row in report["people"]}
    a, b = by_address["a@example.org"], by_address["b@example.org"]
    assert len(person_index_path(tmp_path, a).read_text().splitlines()) == 2
    assert len(person_index_path(tmp_path, b).read_text().splitlines()) == 2
    stored = list((tmp_path / ".state/mail/messages/gmail").glob("*.json"))
    assert len(stored) == 3  # shared message is indexed twice, stored once
    assert all(os.stat(path).st_mode & 0o777 == 0o600 for path in stored)
    assert "body shared" not in (tmp_path / a).read_text()
    # Other people's mail is owner-only at every level, and no page outside
    # .state carries a body.
    for folder in ("mail", "mail/messages", "mail/messages/gmail", "mail/people", "mail/projects"):
        assert os.stat(tmp_path / ".state" / folder).st_mode & 0o777 == 0o700
    pages = [path for path in tmp_path.rglob("*") if path.is_file() and ".state" not in path.parts]
    assert pages and not [path for path in pages if "body shared" in path.read_text(errors="ignore")]
    # Map metadata is persisted by the CLI after archiving; mimic that handoff.
    from connectonion.rem.files import state_path, write_json
    write_json(state_path(tmp_path, "map.json"), {**report, "mail_archive": archive})
    items, coverage = gather("A", ["a@example.org"], days=1, clients={}, subscriptions={},
                             archive_root=tmp_path, record=a)
    assert [item["text"] for item in items] == ["--- Email Body ---\nbody shared",
                                                 "--- Email Body ---\nbody reply"]
    assert any("loaded from private init archive" in note for note in coverage)
    # An org is read from the same archive by domain: no provider, no listing (#1963).
    items, coverage = gather("Example", ["example.org"], days=1, clients={}, subscriptions={},
                             archive_root=tmp_path, record="orgs/example.md")
    assert [item["text"] for item in items] == ["--- Email Body ---\nbody shared",
                                                 "--- Email Body ---\nbody reply",
                                                 "--- Email Body ---\nbody b-reply"]
    assert any("3 loaded from private init archive" in note for note in coverage)
    items, _ = gather("Other", ["other.org"], days=1, clients={}, subscriptions={},
                      archive_root=tmp_path, record="orgs/other.md")
    assert items == []
    class DeltaMail:
        calls = []
        attachments = []
        def my_addresses(self): return {"me@example.org"}
        def list_with(self, address, start, end):
            self.calls.append((address, start, end))
            return []
        def download_attachments(self, message_id, folder):
            self.attachments.append(message_id)
            if message_id != "shared":
                return []
            path = Path(folder) / "decision.txt"
            path.write_text("Decision attached", encoding="utf-8")
            return [str(path)]
    delta = DeltaMail()
    items, _ = gather("A", ["a@example.org"], days=1, clients={"gmail": delta}, subscriptions={},
                      archive_root=tmp_path, record=a, attachments_dir=tmp_path / ".state/attachments")
    assert len(delta.calls) == 1
    assert delta.calls[0][1] >= archive["range_end"]
    assert delta.attachments == ["shared", "reply"]
    assert any(item["role"] == "attachment" and item["text"] == "Decision attached" for item in items)


def test_init_archive_builds_project_source_file(tmp_path, monkeypatch):
    rem = tmp_path / "notebook"
    prepare(rem)
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
    monkeypatch.setattr("connectonion.rem.map.scan_projects", scan)
    report = build_map(rem, subscription, {}, days=1, skill_directories=[skills],
                       capture_sources=True)
    archive = archive_init(rem, report, {})
    assert archive["project_indexes"] == 1
    index = project_index_path(rem, report["projects"][0]["record"])
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


# ------------------------------------------- the 1.9.0a6 acceptance run (#2035)

T0 = datetime(2026, 9, 30, 9, 0, tzinfo=timezone.utc)


class Bodies:
    def __init__(self):
        self.calls = []

    def get_email_body(self, message_id):
        self.calls.append(message_id)
        return f"--- Email Body ---\nbody {message_id}"


class Clock:
    """A monotonic clock that moves 10 seconds a reading."""
    def __init__(self):
        self.value = 0.0

    def __call__(self):
        self.value += 10
        return self.value


def _inventory(root, count=6):
    from connectonion.rem.files import atomic_write, state_path, write_json
    rows = [{"type": "mail", "source": "gmail", "id": f"m{n}", "date": (T0 - timedelta(days=n)).isoformat(),
             "from": "a@example.org", "to": ["me@example.org"], "cc": [], "subject": f"S{n}"} for n in range(count)]
    atomic_write(state_path(root, "source-inventory.jsonl"), "".join(json.dumps(row) + "\n" for row in rows))
    report = {"started": T0.isoformat(), "days": 90, "people": [], "projects": [], "errors": [],
              "owner": {"record": "people/me.md", "addresses": ["me@example.org"]}}
    write_json(state_path(root, "map.json"), report)
    return report


def test_a_stalled_archive_says_so_with_the_command_that_resumes_it(tmp_path):
    """#2035: archive.json sat at `phase: running` (550 of 3,152) for a day and status said nothing."""
    from connectonion.rem.files import read_json, state_path, write_json
    from connectonion.rem.mail_archive import archive_state
    prepare(tmp_path)
    report = _inventory(tmp_path)
    paused = archive_init(tmp_path, report, {"gmail": Bodies()}, seconds=25, clock=Clock(), now=lambda: T0)
    assert paused["phase"] == "paused" and paused["saved"] == 2
    manifest = read_json(state_path(tmp_path, "mail/archive.json"), {})
    assert manifest["updated"] == T0.isoformat()
    write_json(state_path(tmp_path, "mail/archive.json"), {**manifest, "phase": "running"})   # the process died

    fresh = archive_state(tmp_path, now=T0 + timedelta(minutes=2))
    assert fresh["phase"] == "running" and not fresh["stalled"]
    stalled = archive_state(tmp_path, now=T0 + timedelta(hours=20))
    assert stalled["stalled"] and (stalled["on_disk"], stalled["target"]) == (2, 6)
    assert "no progress since 2026-09-30T09:00" in stalled["summary"]
    assert "co rem sync" in stalled["summary"]
    write_json(state_path(tmp_path, "mail/archive.json"), {**manifest, "phase": "complete"})
    assert archive_state(tmp_path, now=T0) is None                       # nothing to say


def test_the_next_sync_resumes_from_the_bodies_already_saved(tmp_path):
    from connectonion.rem.mail_archive import archive_state, resume_stalled
    prepare(tmp_path)
    report = _inventory(tmp_path)
    archive_init(tmp_path, report, {"gmail": Bodies()}, seconds=25, clock=Clock(), now=lambda: T0)
    mail = Bodies()

    later = T0 + timedelta(hours=20)
    first = resume_stalled(tmp_path, {"gmail": mail}, seconds=25, clock=Clock(), now=lambda: later)
    assert first["phase"] == "paused" and first["reused"] == 2 and mail.calls == ["m2", "m3"]
    assert resume_stalled(tmp_path, {"gmail": mail}, now=lambda: later) is None   # paused just now: not stalled
    done = resume_stalled(tmp_path, {"gmail": mail}, now=lambda: later + timedelta(hours=1))
    assert done["phase"] == "complete" and done["reused"] == 4 and mail.calls == ["m2", "m3", "m4", "m5"]
    assert archive_state(tmp_path, now=later + timedelta(hours=9)) is None
    assert resume_stalled(tmp_path, {"gmail": mail}, now=lambda: later + timedelta(hours=9)) is None


def test_a_stalled_archive_waits_when_its_mailbox_cannot_be_read(tmp_path):
    from connectonion.rem.mail_archive import resume_stalled
    prepare(tmp_path)
    archive_init(tmp_path, _inventory(tmp_path), {"gmail": Bodies()}, seconds=25, clock=Clock(), now=lambda: T0)
    left = resume_stalled(tmp_path, {}, now=lambda: T0 + timedelta(hours=20))
    assert left == {"phase": "paused", "resumed": False, "reason": "gmail unavailable"}


def test_status_shows_an_incomplete_archive(tmp_path):
    from connectonion.rem.service import status
    prepare(tmp_path)
    archive_init(tmp_path, _inventory(tmp_path), {"gmail": Bodies()}, seconds=25, clock=Clock(), now=lambda: T0)
    shown = status(tmp_path)["mail_archive"]
    assert shown["phase"] == "paused" and (shown["on_disk"], shown["target"]) == (2, 6)


# ------------------------------------------- the 1.9.0a7 acceptance run (#2042)


def _with_person(root):
    from connectonion.rem.files import state_path, write_json
    report = _inventory(root)
    report["people"] = [{"record": "people/a.md", "addresses": ["a@example.org"]}]
    write_json(state_path(root, "map.json"), report)
    return report


class Listing(Bodies):
    """A mailbox that lists the six inventory messages and serves their bodies."""

    def my_addresses(self):
        return {"me@example.org"}

    def list_with(self, address, start, end):
        return [{"id": f"m{n}", "date": (T0 - timedelta(days=n)).isoformat(), "from": "a@example.org",
                 "to": ["me@example.org"], "subject": f"S{n}"} for n in range(6)]


def test_an_investigation_reads_the_bodies_a_paused_archive_saved_and_fetches_only_the_rest(tmp_path):
    """#2042: 2,693 of 3,152 bodies were saved and every investigation said
    "0 loaded from private init archive" and fetched all of them again."""
    prepare(tmp_path)
    report = _with_person(tmp_path)
    paused = archive_init(tmp_path, report, {"gmail": Bodies()}, seconds=25, clock=Clock(), now=lambda: T0)
    assert paused["phase"] == "paused" and paused["people_indexes"] == 2   # indexed at the pause, not only at the end
    mail = Listing()
    items, coverage = gather("A", ["a@example.org"], days=36500, clients={"gmail": mail}, subscriptions={},
                             archive_root=tmp_path, record="people/a.md")
    assert sorted(mail.calls) == ["m2", "m3", "m4", "m5"]          # m0 and m1 came from disk
    assert len(items) == 6
    note = next(line for line in coverage if line.startswith("gmail"))
    assert "2 loaded from private init archive (2 of 6 bodies saved so far)" in note
    assert "searched on the server for a@example.org" in note     # the rest still asked the mailbox


def test_an_org_reads_a_paused_archive_too(tmp_path):
    prepare(tmp_path)
    archive_init(tmp_path, _with_person(tmp_path), {"gmail": Bodies()}, seconds=25, clock=Clock(), now=lambda: T0)
    items, coverage = gather("Example", ["example.org"], days=36500, clients={}, subscriptions={},
                             archive_root=tmp_path, record="orgs/example.md")
    assert [item["subject"] for item in items] == ["S1", "S0"]
    assert any("2 loaded from private init archive (2 of 6 bodies saved so far)" in line for line in coverage)


def test_a_sync_that_resumes_the_archive_says_how_far_it_has_got(tmp_path):
    """#2042: a sync spent 5 minutes saving bodies under "Reading new material…" and said nothing else."""
    from connectonion.rem.mail_archive import resume_stalled
    prepare(tmp_path)
    archive_init(tmp_path, _inventory(tmp_path), {"gmail": Bodies()}, seconds=25, clock=Clock(), now=lambda: T0)
    said = []
    resume_stalled(tmp_path, {"gmail": Bodies()}, now=lambda: T0 + timedelta(hours=20), say=said.append)
    assert said[0] == "Saving mail bodies: 2 of 6 saved by init; resuming for at most 5 minutes"
    assert said[-1] == "Saving mail bodies: 6 of 6, done"
    assert len(said) <= 12

def test_one_missing_body_does_not_take_the_whole_archive_away(tmp_path):
    """A real first run (2026-10-01): 1 of 1,883 bodies timed out, the archive
    was 'partial', and every person and organisation page skipped it for server
    searches -- 62 pages found nothing under 16 parallel searches. Only a page
    that needs the missing message falls back."""
    from connectonion.rem.mail_archive import domain_material, person_material
    prepare(tmp_path)
    skills = tmp_path / "source-skills"
    skills.mkdir()
    when = (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat()
    rows = [{"id": "one", "date": when, "from": "Alice Alpha <a@alpha.example>", "to": ["me@example.org"], "subject": "Plan"},
            {"id": "two", "date": when, "from": "Bob Beta <b@beta.example>", "to": ["me@example.org"], "subject": "Plan"},
            {"id": "three", "date": when, "from": "me@example.org", "to": ["a@alpha.example"], "subject": "Re: Plan"},
            {"id": "four", "date": when, "from": "me@example.org", "to": ["b@beta.example"], "subject": "Re: Plan"}]

    class Mail:
        def my_addresses(self): return {"me@example.org"}
        def list_between(self, start, end, limit): return [r for r in rows if start <= r["date"] < end]
        def get_email_body(self, message_id):
            if message_id == "two":
                raise TimeoutError("read timed out")
            return f"body {message_id}"

    report = build_map(tmp_path, {}, {"gmail": Mail()}, days=1, skill_directories=[skills], capture_sources=True)
    archive = archive_init(tmp_path, report, {"gmail": Mail()})
    assert archive["phase"] == "partial" and archive["failed"] == 1
    by_address = {row.get("address"): row["record"] for row in report["people"]}
    assert person_material(tmp_path, by_address["a@alpha.example"]) is not None
    beta = person_material(tmp_path, by_address["b@beta.example"])
    assert beta is not None  # the sent reply remains available despite one missing incoming body
    assert "body four" in str(beta) and "body two" not in str(beta)
    assert domain_material(tmp_path, ["alpha.example"]) is not None
