"""SQLite v3 storage, search privacy and disposable-scratch regressions (#3468, #3469)."""

import hashlib
import json
import os
import sqlite3
from contextlib import closing

import pytest

from connectonion.rem import attachments, store
from connectonion.rem.config import prepare
from connectonion.rem.files import Notebook, state_path, write_json
from connectonion.rem.store_build import SCHEMA_VERSION
from connectonion.rem.translate import digest


@pytest.fixture
def notebook(tmp_path):
    prepare(tmp_path)
    book = Notebook(tmp_path)
    book.write("people/alice.md", "# Alice\n\nA fictional teammate.\n\n## Facts\n- Role: Engineer\n")
    book.write("orgs/acme.md", "# Acme\n\nA fictional organisation.\n")
    book.write("projects/pilot.md", "# Pilot\n\nA fictional pilot.\n\n[Alice](../people/alice.md)\n")
    write_json(state_path(tmp_path, "map.json"), {
        "people": [{"record": "people/alice.md", "address": "alice@example.test", "mails": 3}],
        "orgs": [{"record": "orgs/acme.md", "domain": "acme.example", "people": ["people/alice.md"]}],
    })
    return tmp_path, book


def _write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    before = path.stat().st_mtime_ns if path.exists() else 0
    path.write_text(text, encoding="utf-8")
    stamp = max(path.stat().st_mtime_ns, before + 1_000_000)
    os.utime(path, ns=(stamp, stamp))
    return path


def _translate(root, record, text):
    original = Notebook(root).read(record)
    return _write(state_path(root, f"translations/zh/{record}"),
                  f"<!-- co rem translation of {record} sha256:{digest(original)} -->\n{text}")


def test_writer_pragmas_persist_and_old_schema_or_wrong_vacuum_rebuilds(notebook):
    root, _ = notebook
    assert SCHEMA_VERSION == "3"
    for mode in ("fresh", "old-schema", "wrong-vacuum", "full-vacuum"):
        if mode != "fresh":
            store.db_path(root).unlink()
            with closing(sqlite3.connect(store.db_path(root))) as db:
                if mode == "full-vacuum":
                    db.execute("pragma auto_vacuum=full")
                db.execute("create table meta (key text primary key, value text)")
                db.execute("insert into meta values ('schema_version', ?)", ("2" if mode == "old-schema" else "3",))
                db.commit()
                assert db.execute("pragma auto_vacuum").fetchone()[0] == (1 if mode == "full-vacuum" else 0)
        store.refresh(root)
        with closing(store._connect(store.db_path(root))) as db:
            assert db.execute("pragma journal_mode").fetchone()[0] == "wal"
            assert db.execute("pragma auto_vacuum").fetchone()[0] == 2
            assert db.execute("pragma synchronous").fetchone()[0] == 1
            assert db.execute("pragma foreign_keys").fetchone()[0] == 1
            assert db.execute("pragma foreign_key_check").fetchall() == []
        with closing(sqlite3.connect(store.db_path(root))) as db:
            assert db.execute("pragma auto_vacuum").fetchone()[0] == 2
            assert db.execute("pragma journal_mode").fetchone()[0] == "wal"


def test_joined_page_and_map_edits_only_write_changed_records(notebook, monkeypatch):
    root, book = notebook
    store.refresh(root)
    sql = []
    connect = store._connect

    def traced(file):
        db = connect(file)
        db.set_trace_callback(sql.append)
        return db

    monkeypatch.setattr(store, "_connect", traced)
    with closing(sqlite3.connect(store.db_path(root))) as db:
        untouched = db.execute("select rowid, * from records where record = 'projects/pilot.md'").fetchone()
    for record, text in (("people/alice.md", "# Alice\n\nA fictional teammate.\n\n## Facts\n- Role: Founder\n- Last contact: 2040-02-03\n"),
                         ("orgs/acme.md", "# Acme Studio\n\nUpdated fictional organisation.\n")):
        book.write(record, text)
        store.refresh(root)
    mapped = json.loads(state_path(root, "map.json").read_text())
    mapped["people"][0]["mails"] = 9
    write_json(state_path(root, "map.json"), mapped)
    store.refresh(root)
    person = store.person(root, "people/alice.md")
    assert person["role"] == "Founder" and person["mails"] == 9
    assert store._rows(root, "select name, last_contact from orgs")[0] == {
        "name": "Acme Studio", "last_contact": "2040-02-03"}
    assert all("where" in statement.lower() for statement in sql
               if statement.lower().startswith("delete from ")
               and statement.lower().split()[2] in {"records", "people", "orgs", "projects", "edges", "links"})
    assert not any(statement.lower().startswith("insert into records ") and "projects/pilot.md" in statement
                   for statement in sql)
    with closing(sqlite3.connect(store.db_path(root))) as db:
        assert db.execute("select rowid, * from records where record = 'projects/pilot.md'").fetchone() == untouched
        assert db.execute("pragma freelist_count").fetchone()[0] <= 64
    book.delete("people/alice.md")
    store.refresh(root)
    assert store.person(root, "people/alice.md") is None
    assert store.edges(root, "people/alice.md") == []
    with closing(store._connect(store.db_path(root))) as db:
        assert db.execute("pragma foreign_key_check").fetchall() == []
        db.execute("delete from records where record = 'orgs/acme.md'")
        assert db.execute("select * from orgs").fetchall() == []


def test_external_content_fts_triggers_and_literal_cjk_search_preserve_privacy(notebook):
    root, book = notebook
    book.write("knowledge/terms.md", "# Terms\n\nA public overview.\n\n## Agreement\n合同条款要求提前续签。\n\n"
               "## Private [personal]\n秘密续签凭证 medicalsecret.\n")
    book.write("knowledge/private.md", "# Hidden [sensitive]\n\n合同条款 hiddencontract.\n")
    store.refresh(root)
    with closing(sqlite3.connect(store.db_path(root))) as db:
        assert db.execute("select name from sqlite_master where name = 'records_fts_content'").fetchall() == []
        assert "content='records'" in db.execute("select sql from sqlite_master where name = 'records_fts'").fetchone()[0]
        assert db.execute("select record from records_fts where records_fts match 'overview'").fetchall() == [
            ("knowledge/terms.md",)]
    for level in ("cover", "public"):
        for query in ("合同条款", "续签", "overview", "vervie"):
            hits = store.search(root, query, max_privacy=level, privacy="all")
            assert [hit["record"] for hit in hits] == ["knowledge/terms.md"]
            assert hits[0]["snippet"] and "秘密" not in hits[0]["snippet"]
            assert "public_body" not in hits[0]
        for query in ("秘密续签凭证", "medicalsecret", "hiddencontract", "%", "' OR 1=1 --"):
            assert store.search(root, query, max_privacy=level) == []
    book.write("knowledge/terms.md", "# Terms\n\nReplacement wording.\n")
    store.refresh(root)
    assert store.search(root, "overview") == []
    assert store.search(root, "Replacement")[0]["record"] == "knowledge/terms.md"
    book.delete("knowledge/terms.md")
    store.refresh(root)
    assert store.search(root, "Replacement") == []
    with closing(sqlite3.connect(store.db_path(root))) as db:
        db.execute("insert into records_fts(records_fts, rank) values ('integrity-check', 1)")


def test_fts_operational_failure_uses_body_substring_fallback(notebook, monkeypatch):
    root, book = notebook
    book.write("knowledge/terms.md", "# Terms\n\nOverview.\n\n## Details\nRenewal clause.\n")
    store.refresh(root)
    rows = store._rows

    def unavailable(root, sql, parameters=()):
        if "records_fts match" in sql:
            from connectonion.rem.files import RemError
            raise RemError(store.UNREADABLE) from sqlite3.OperationalError("FTS unavailable")
        return rows(root, sql, parameters)

    monkeypatch.setattr(store, "_rows", unavailable)
    assert store.search(root, "Renewal")[0]["record"] == "knowledge/terms.md"


def test_caches_extract_once_detect_in_place_edits_and_remove_vanished_files(notebook, monkeypatch):
    root, _ = notebook
    source = "gmail:123456789abc:terms.txt"
    attachment = _write(state_path(root, "attachments/gmail/123456789abc/terms.txt"), "Initial terms")
    translation = _translate(root, "people/alice.md", "# Alice\n\n虚构的同事。\n")
    url = "https://acme.example/terms"
    identity = hashlib.sha256(url.encode()).hexdigest()
    capture = state_path(root, f"research/{identity}/2040-01-01-initial.json")
    _write(capture, json.dumps({"source": url, "timestamp": "2040-01-01", "title": "Terms", "text": "Initial terms"}))
    private = _write(capture.with_name("2040-01-02-private.json"), json.dumps({
        "source": url, "timestamp": "2040-01-02", "text": "Private terms [sensitive]"}))
    extracted, extract = [], attachments.extract_text

    def track(path, limit):
        extracted.append(path)
        return extract(path, limit=limit)

    monkeypatch.setattr(attachments, "extract_text", track)
    store.refresh(root)
    assert extracted == [attachment]
    assert store.attachment_row(root, source)["extracted_text"] == "Initial terms"
    assert store.attachments_map(root, [source])[source]["mime_type"] == "text/plain"
    assert store.attachments_map(root, []) == {}
    assert store.translations_map(root) == {"people/alice.md": {"zh": "# Alice\n\n虚构的同事。\n"}}
    assert len(store.research_for_sources(root, [url])[url]) == 1
    assert len(store.research_for_sources(root, [url], private=True)[url]) == 2
    store.refresh(root)
    assert extracted == [attachment]
    _write(attachment, "Revised terms")  # Same length; the message directory mtime stays unchanged.
    _translate(root, "people/alice.md", "# Alice\n\n更新的同事。\n")
    _write(capture, json.dumps({"source": url, "timestamp": "2040-01-01", "title": "New terms", "text": "Revised terms"}))
    store.refresh(root)
    assert extracted == [attachment, attachment]
    assert store.attachment_row(root, source)["extracted_text"] == "Revised terms"
    assert "更新" in store.translations_map(root, ["people/alice.md"])["people/alice.md"]["zh"]
    assert store.research_for_sources(root, [url])[url][0]["title"] == "New terms"
    for path in (attachment, translation, capture, private):
        path.unlink()
    store.refresh(root)
    assert store.attachments_map(root) == {}
    assert store.translations_map(root) == {}
    assert store.research_for_sources(root, [url], private=True) == {}


def test_unchanged_caches_do_not_relist_directories_read_files_or_write_db(notebook, monkeypatch):
    from pathlib import Path

    root, _ = notebook
    _write(state_path(root, "attachments/gmail/123456789abc/terms.txt"), "Initial terms")
    _translate(root, "people/alice.md", "# Alice\n\n虚构的同事。\n")
    store.refresh(root)
    read, listing, connect = Path.read_text, Path.iterdir, store._connect
    changes = []

    def no_cache_reads(path, *args, **kwargs):
        assert not any(kind in path.parts for kind in ("attachments", "translations", "research"))
        return read(path, *args, **kwargs)

    def no_cache_listings(path):
        assert not any(kind in path.parts for kind in ("attachments", "translations", "research"))
        return listing(path)

    def track(file):
        db = connect(file)
        db.set_trace_callback(changes.append)
        return db

    monkeypatch.setattr(Path, "read_text", no_cache_reads)
    monkeypatch.setattr(Path, "iterdir", no_cache_listings)
    monkeypatch.setattr(store, "_connect", track)
    assert store.refresh(root)["rebuilt"] == []
    assert not any(sql.lower().startswith(("insert", "update", "delete", "begin")) for sql in changes)


def test_translation_cache_invalidates_when_original_changes_or_disappears(notebook):
    root, book = notebook
    _translate(root, "people/alice.md", "# Alice\n\n虚构的同事。\n")
    store.refresh(root)
    assert store.translations_map(root)
    book.write("people/alice.md", "# Alice\n\nChanged original.\n")
    store.refresh(root)
    assert store.translations_map(root) == {}
    _translate(root, "people/alice.md", "# Alice\n\n已更新。\n")
    store.refresh(root)
    assert store.translations_map(root)
    book.delete("people/alice.md")
    store.refresh(root)
    assert store.translations_map(root) == {}


def test_large_page_shrink_reclaims_freelist_pages(notebook):
    root, book = notebook
    book.write("knowledge/large.md", "# Large\n\n" + "Fictional contract terms. " * 30_000)
    store.refresh(root)
    before = store.db_path(root).stat().st_size
    book.write("knowledge/large.md", "# Large\n\nShort terms.\n")
    store.refresh(root)
    with closing(sqlite3.connect(store.db_path(root))) as db:
        assert db.execute("pragma freelist_count").fetchone()[0] < 8
    assert store.db_path(root).stat().st_size < before


def test_project_link_edits_preserve_links_from_people_pages(notebook):
    root, book = notebook
    book.write("people/alice.md", book.read("people/alice.md") + "\n[Pilot](../projects/pilot.md)\n")
    store.refresh(root)
    assert store.edges(root, "projects/pilot.md")[0]["count"] == 2
    book.write("projects/pilot.md", "# Pilot\n\nNo outgoing links.\n")
    store.refresh(root)
    assert store.edges(root, "projects/pilot.md")[0]["count"] == 1
    incremental = store.edges(root, "projects/pilot.md")
    store.db_path(root).unlink()
    store.refresh(root)
    assert store.edges(root, "projects/pilot.md") == incremental


def test_note_translation_invalidates_without_indexed_note_rows(notebook):
    root, book = notebook
    record = "notes/pilot.md"
    book.write(record, "# Pilot note\n\nAn initial fictional note.\n")
    _translate(root, record, "# Pilot note\n\n最初的笔记。\n")
    store.refresh(root)
    assert store.translations_map(root, [record])
    assert store._rows(root, "select * from records where record = ?", [record]) == []
    book.write(record, "# Pilot note\n\nA changed fictional note.\n")
    store.refresh(root)
    assert store.translations_map(root, [record]) == {}
    _translate(root, record, "# Pilot note\n\n已修改的笔记。\n")
    store.refresh(root)
    assert store.translations_map(root, [record])
    book.delete(record)
    store.refresh(root)
    assert store.translations_map(root, [record]) == {}


def test_caches_never_extract_symlinked_files_or_directories(notebook, monkeypatch):
    root, _ = notebook
    external = root / "external"
    external.mkdir()
    original = _write(external / "terms.txt", "Fictional material outside the cache tree")
    provider = state_path(root, "attachments/gmail")
    provider.mkdir(parents=True)
    (provider / "linked-message").symlink_to(external, target_is_directory=True)
    message = provider / "123456789abc"
    message.mkdir()
    (message / "terms.txt").symlink_to(original)

    def never_extract(*args, **kwargs):
        pytest.fail("A symlink must never be extracted")

    monkeypatch.setattr(attachments, "extract_text", never_extract)
    store.refresh(root)
    assert store.attachments_map(root) == {}
