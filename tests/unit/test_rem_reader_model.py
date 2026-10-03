"""Navigation links and change cards must keep their evidence boundaries."""

from datetime import datetime, timezone
from pathlib import Path
import pytest

from connectonion.rem.claim_changes import material_changes
from connectonion.rem.reader import snapshot
from connectonion.rem.reader_model import relationships


def test_attachment_citation_with_spaces_reads_current_file_without_claiming_old_capture(tmp_path):
    from connectonion.rem.config import prepare
    from connectonion.rem.files import state_path
    from connectonion.rem.reader_model import cited_context

    prepare(tmp_path)
    source = 'outlook:123456789abc:Returned client agreement.txt'
    path = state_path(tmp_path, 'attachments/outlook/123456789abc/Returned client agreement.txt')
    path.parent.mkdir(parents=True)
    path.write_text('Example Client Ltd is the collaborator.')
    context = cited_context(tmp_path, [{'text': f'## Sources\n- [15] {source} — 2026-04-13'}])
    assert list(context) == [source]
    assert 'Example Client Ltd' in context[source]['excerpt']
    assert 'Original capture time' in context[source]['input_scope']
    assert 'unknown' in context[source]['input_scope']
    assert not context[source].get('captured_at')


def test_pdf_source_preview_reads_only_the_pages_needed(tmp_path, monkeypatch):
    from connectonion.rem.attachments import attachment_context, extract_text
    from connectonion.rem.config import prepare
    from connectonion.rem.files import state_path

    prepare(tmp_path)
    source = 'outlook:123456789abc:terms.pdf'
    path = state_path(tmp_path, 'attachments/outlook/123456789abc/terms.pdf')
    path.parent.mkdir(parents=True)
    path.write_bytes(b'%PDF-1.4\n')
    first = 'First page clause. ' * 50
    calls = []

    class Page(dict):
        def __init__(self, label, body):
            self.label, self.body = label, body

        def extract_text(self):
            calls.append(self.label)
            return self.body

    class Reader:
        def __init__(self, path):
            self.pages = [Page('first', first), Page('second', 'Later clause.')]

    monkeypatch.setattr('pypdf.PdfReader', Reader)
    context = attachment_context(tmp_path, source)
    assert context['excerpt'] == first.strip()[:640]
    assert context['truncated']
    assert calls == ['first']
    calls.clear()
    assert extract_text(path, limit=None).endswith('Later clause.')
    assert calls == ['first', 'second']


def test_attachment_citation_rejects_a_linked_attachment(tmp_path):
    from connectonion.rem.attachments import attachment_context
    from connectonion.rem.config import prepare
    from connectonion.rem.files import RemError, state_path

    prepare(tmp_path)
    outside = tmp_path / 'outside.txt'
    outside.write_text('Not an archived attachment')
    path = state_path(tmp_path, 'attachments/outlook/123456789abc/linked.txt')
    path.parent.mkdir(parents=True)
    path.symlink_to(outside)
    with pytest.raises(RemError, match='Symlinks'):
        attachment_context(tmp_path, 'outlook:123456789abc:linked.txt')
    assert attachment_context(tmp_path, 'outlook:123456789abc:../outside.txt') is None


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


def test_unicode_case_insensitive_mentions_keep_dotted_and_dotless_i():
    records = [
        {"path": "people/ipek.md", "category": "people", "title": "Ipek Kaya", "text": "# Ipek Kaya"},
        {"path": "projects/pilot.md", "category": "projects", "title": "Pilot",
         "text": "İpek Kaya joined the pilot [1].\n## Sources\n- [1] mail:source — evidence"},
    ]
    assert {link["path"] for link in relationships(records)["projects/pilot.md"]} == {"people/ipek.md"}
    records[1]["text"] = "ıpek Kaya joined the pilot [1]."
    assert {link["path"] for link in relationships(records)["projects/pilot.md"]} == {"people/ipek.md"}


def test_mapped_stubs_keep_explicit_links_without_inventing_prose_relationships():
    records = [
        {"path": "people/mara.md", "category": "people", "title": "Mara Ostrowski", "written": False,
         "text": "# Mara\n\nHarbour was named in metadata. [Fernhill Labs](../orgs/fernhill.md) is linked."},
        {"path": "orgs/fernhill.md", "category": "orgs", "title": "Fernhill Labs", "text": "# Fernhill"},
        {"path": "projects/harbour.md", "category": "projects", "title": "Harbour", "text": "# Harbour"},
    ]
    assert {link["path"] for link in relationships(records)["people/mara.md"]} == {"orgs/fernhill.md"}


def test_relationship_basis_keeps_privacy_after_its_text_is_clipped():
    text = 'Mara Ostrowski discussed confidential background ' + 'detail ' * 40 + '[sensitive] [1].'
    records = [
        {"path": "people/mara.md", "category": "people", "title": "Mara Ostrowski", "text": "# Mara"},
        {"path": "projects/harbour.md", "category": "projects", "title": "Harbour", "text": text},
    ]
    links = relationships(records)
    forward = links['projects/harbour.md'][0]
    reverse = links['people/mara.md'][0]
    assert '[sensitive]' not in forward['basis']
    assert forward['private'] and reverse['private']
    records[1]['text'] = 'Mara Ostrowski discussed the public pilot [1].'
    assert not relationships(records)['projects/harbour.md'][0]['private']


def test_explicit_links_keep_their_own_line_even_after_a_reverse_mention():
    records = [
        {"path": "people/mara.md", "category": "people", "title": "Mara Ostrowski",
         "text": "Harbour is a possible project.\n"},
        {"path": "projects/harbour.md", "category": "projects", "title": "Harbour",
         "text": "Mara is in an old directory.\n"
                 "The pilot involved [our contact](../people/mara.md) [sensitive] [2][2][3].\n"},
    ]
    links = relationships(records)
    assert links == relationships(list(reversed(records)))
    forward = links['projects/harbour.md'][0]
    assert forward['kind'] == 'linked'
    assert forward['basis'].startswith('The pilot involved our contact')
    assert forward['sources'] == ['2', '3'] and forward['private']
    assert forward['via'] == 'projects/harbour.md'
    # The opposite page has its own weaker statement, with its own provenance.
    reverse = links['people/mara.md'][0]
    assert reverse['kind'] == 'mentioned'
    assert reverse['sources'] == [] and not reverse['private']
    assert reverse['via'] == 'people/mara.md'


def test_exact_path_links_include_skills_and_ignore_urls_and_source_trailers():
    records = [
        {"path": "people/mara.md", "category": "people", "title": "Mara Ostrowski",
         "text": "Use [playbook](../skills/catalog/triage.md) [3].\n"
                 "External [guide](https://example.test/projects/harbour.md).\n"
                 "## Sources\n- [3] See [Harbour](../projects/harbour.md)"},
        {"path": "skills/catalog/triage.md", "category": "skills", "title": "Triage",
         "text": "# Triage"},
        {"path": "projects/harbour.md", "category": "projects", "title": "Harbour",
         "text": "# Harbour"},
    ]
    links = relationships(records)
    assert [r['path'] for r in links['people/mara.md']] == ['skills/catalog/triage.md']
    link = links['people/mara.md'][0]
    assert link['kind'] == 'linked' and link['sources'] == ['3']
    incoming = links['skills/catalog/triage.md'][0]
    assert incoming['kind'] == 'linked from'
    assert incoming['via'] == 'people/mara.md' and incoming['sources'] == ['3']


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


def test_mail_source_dialog_keeps_a_reply_request_beyond_the_old_preview_limit(tmp_path):
    import hashlib
    from connectonion.rem.config import prepare
    from connectonion.rem.files import atomic_write, state_path, write_json
    from connectonion.rem.mail_archive import message_path
    from connectonion.rem.reader_model import cited_context
    from connectonion.rem.store import refresh

    prepare(tmp_path)
    native = 'long-reply-request'
    source = 'outlook:' + hashlib.sha256(native.encode()).hexdigest()[:12]
    body = 'Background. ' * 700 + 'Please reply with the proposed time.'
    write_json(message_path(tmp_path, 'outlook', native), {'id': native, 'provider': 'outlook', 'body': body})
    import json
    atomic_write(state_path(tmp_path, 'source-inventory.jsonl'), json.dumps({
        'type': 'mail', 'source': 'outlook', 'id': native, 'from': 'alex@example.org',
        'date': '2026-09-30T10:00:00+00:00', 'subject': 'Next meeting'}) + '\n')
    refresh(tmp_path)

    context = cited_context(tmp_path, [{'text': '## Sources\n- [1] ' + source}])[source]
    assert context['excerpt'] == body
    assert not context['truncated']


def test_an_empty_retained_calendar_reply_keeps_its_header_evidence(tmp_path):
    import hashlib
    from connectonion.rem.config import prepare
    from connectonion.rem.mail_archive import retain_message
    from connectonion.rem.reader_model import cited_context
    from connectonion.rem.store import refresh

    prepare(tmp_path)
    row = {'id': 'empty-acceptance', 'from': 'me@owner.example', 'to': ['events@example.org'],
           'cc': [], 'date': '2026-08-28T23:34:32Z', 'subject': 'Accepted: Workshop',
           'thread_id': 'calendar-thread'}
    raw = 'From: me@owner.example\nTo: events@example.org\nSubject: Accepted: Workshop\nDate: 2026-08-28T23:34:32Z\n\n--- Email Body ---\n\n'
    retain_message(tmp_path, 'outlook', row, raw, fetched_at='2026-10-02T10:00:00Z')
    refresh(tmp_path)
    source = 'outlook:' + hashlib.sha256(row['id'].encode()).hexdigest()[:12]
    context = cited_context(tmp_path, [{'text': '## Sources\n- [1] ' + source}])[source]
    assert context['body_empty'] and context['excerpt'] == '' and not context['truncated']
    assert context['subject'] == row['subject']
    assert datetime.fromisoformat(context['time']) == datetime.fromisoformat(row['date'].replace('Z', '+00:00'))
    assert context['participants']['from'] == row['from']
    assert context['participants']['to'] == row['to']
    assert context['captured_at'] == '2026-10-02T10:00:00Z'


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


@pytest.mark.parametrize('saved_provider,saved_id', [('outlook', 'different-native'), ('gmail', 'native')])
def test_mail_citation_rejects_mismatched_snapshot_identity(tmp_path, saved_provider, saved_id):
    import hashlib, json
    from connectonion.rem.config import prepare
    from connectonion.rem.files import atomic_write, state_path, write_json
    from connectonion.rem.mail_archive import message_path
    from connectonion.rem.reader_model import cited_context
    from connectonion.rem.store import refresh
    prepare(tmp_path)
    write_json(message_path(tmp_path, 'outlook', 'native'), {
        'provider': saved_provider, 'id': saved_id, 'body': 'Another message, not the cited original.'})
    atomic_write(state_path(tmp_path, 'source-inventory.jsonl'), json.dumps({
        'type': 'mail', 'source': 'outlook', 'id': 'native', 'date': '2026-09-30T10:00:00Z'}) + '\n')
    refresh(tmp_path)
    source = 'outlook:' + hashlib.sha256(b'native').hexdigest()[:12]
    assert cited_context(tmp_path, [{'text': '## Sources\n- [1] ' + source}]) == {}
