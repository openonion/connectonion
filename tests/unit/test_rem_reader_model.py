"""Navigation links and change cards must keep their evidence boundaries."""

from datetime import datetime, timezone
from pathlib import Path

from connectonion.rem.claim_changes import material_changes
from connectonion.rem.reader import snapshot
from connectonion.rem.reader_model import relationships


def test_short_mentions_link_only_when_the_alias_is_unique():
    records = [
        {"path": "people/mara.md", "category": "people", "title": "Mara Ostrowski", "text": "# Mara"},
        {"path": "orgs/fernhill.md", "category": "orgs", "title": "Fernhill Labs", "text": "# Fernhill"},
        {"path": "projects/harbour.md", "category": "projects", "title": "Harbour",
         "text": "# Harbour\nMara met Fernhill about the pilot [1].\n## Sources\n- [1] mail:source — Mara"},
    ]
    links = relationships(records)
    assert {link["path"] for link in links["projects/harbour.md"]} == {"people/mara.md", "orgs/fernhill.md"}
    assert all(link["kind"] == "cited mention" for link in links["projects/harbour.md"])
    records.append({"path": "people/mara-other.md", "category": "people", "title": "Mara Nguyen", "text": "# Mara"})
    links = relationships(records)
    assert {link["path"] for link in links["projects/harbour.md"]} == {"orgs/fernhill.md"}


def test_claim_changes_require_a_cited_new_value_and_do_not_count_formatting():
    before = {"people/mara.md": "# Mara\n\n## Facts\n- Role: Partnerships Lead [1]\n- Phone: Unknown\n"}
    after = {"people/mara.md": "# Mara\n\n## Facts\n- Role: partnerships-lead [2]\n- Phone: +64 21 123 [3]\n- Company: Fernhill\n\n## Sources\n- [2] mail:role — role\n- [3] mail:phone — phone\n"}
    changes = material_changes(before, after, ["people/mara.md"])
    assert [(change["field"], change["after"], change["sources"]) for change in changes] == [
        ("phone", "+64 21 123", ["3"])]
    assert material_changes(before, {"people/mara.md": "# Mara\n\n## Facts\n- Phone: +64 21 123 [3]\n"},
                            ["people/mara.md"]) == []


def test_fixture_carries_original_source_and_bounded_conversation(tmp_path, monkeypatch):
    import sys
    monkeypatch.setattr("connectonion.rem.service.mail_available", lambda kind: False)
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "fixtures"))
    from rem_reader_notebook import build

    data = snapshot(build(tmp_path / "rem", datetime.now(timezone.utc)))
    context = data["source_context"]["outlook:77c09ad1e3f0"]
    assert "usage export" in context["excerpt"]
    thread = data["conversations"][context["thread"]]
    assert thread["total"] == len(thread["messages"]) == 3
    assert [message["id"] for message in thread["messages"]] == [
        "outlook:e4a2c1907bd3", "outlook:77c09ad1e3f0", "gmail:0f9be4c12a55"]
    assert "outlook:9a03f1c2be77" not in data["source_context"]


def test_hashed_mail_citations_resolve_native_provider_ids_without_migrating_them(tmp_path):
    import hashlib
    from connectonion.rem.config import prepare
    from connectonion.rem.files import atomic_write, state_path, write_json
    from connectonion.rem.mail_archive import message_path
    from connectonion.rem.reader_model import cited_context
    from connectonion.rem.store import refresh

    prepare(tmp_path)
    native = 'native/provider-message-id'
    source = 'outlook:' + hashlib.sha256(native.encode()).hexdigest()[:12]
    write_json(message_path(tmp_path, 'outlook', native), {'id': native, 'provider': 'outlook', 'body': 'I accept the credits.'})
    inventory = {'type': 'mail', 'source': 'outlook', 'id': native, 'from': 'me@owner.example',
                 'to': ['alex@example.org'], 'date': '2026-09-30T10:00:00+00:00', 'subject': 'Offer'}
    import json
    atomic_write(state_path(tmp_path, 'source-inventory.jsonl'), json.dumps(inventory) + '\n')
    refresh(tmp_path)
    context = cited_context(tmp_path, [{'text': '## Sources\n- [1] ' + source}])
    assert context[source]['excerpt'] == 'I accept the credits.'
    assert context[source]['sender'] == 'me@owner.example'
    assert context[source]['thread']


def test_hashed_mail_citation_rejects_a_body_pointer_for_a_different_native_id(tmp_path):
    import sqlite3
    from connectonion.rem.config import prepare
    from connectonion.rem.files import state_path
    from connectonion.rem.reader_model import cited_context
    from connectonion.rem.store import refresh
    prepare(tmp_path)
    refresh(tmp_path)
    with sqlite3.connect(state_path(tmp_path, 'rem.db')) as db:
        db.execute("insert into messages (id, source, body_path) values (?, ?, ?)",
                   ('outlook:wrong-id', 'outlook', 'mail/messages/outlook/123456789abc0000.json'))
    assert cited_context(tmp_path, [{'text': '## Sources\n- [1] outlook:123456789abc'}]) == {}
