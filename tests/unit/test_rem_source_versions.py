"""A source that saves versions of a changing record: the page cites one version.

A task tracker saves a task again each time it changes. When a rewrite moves a
line from version 3 of a task to version 5, the old id is an update, not lost
evidence; when nothing replaces it, it is still a loss. The reader shows the
version a page cites, never the newest one. `tick:` is a made-up kind so these
rules stay about every versioned source, not one.
"""

import pytest

from connectonion.rem import source_versions


def _record(source):
    return source.partition("@")[0] if "@" in source else None


SNAPSHOTS = {"tick:T4@3": "Due 2026-11-20", "tick:T4@5": "Due 2026-11-27"}


def _snapshot(root, source):
    text = SNAPSHOTS.get(source)
    return text and {"excerpt": text, "truncated": False, "time": "2026-11-14T09:00:00Z",
                     "sender": "", "thread": "", "source": "tick", "subject": "T4"}


@pytest.fixture(autouse=True)
def tick(monkeypatch):
    monkeypatch.setitem(source_versions.KINDS, "tick",
                        source_versions.Kind(_record, _snapshot))


BEFORE = ('# Atlas\n\n## Where it stands\n- T4 is due 2026-11-20. [1]\n- T5 waits on review. [2]\n'
          '\n## Sources\n- [1] tick:T4@3 — task T4\n- [2] gmail:aaaaaaaaaaaa — 2026-11-10\n')


def test_a_newer_version_of_the_same_record_replaces_the_old_one():
    from connectonion.rem.page_review import dropped, restore_dropped, shrinkage
    after = BEFORE.replace('2026-11-20. [1]', '2026-11-27. [1]').replace('tick:T4@3', 'tick:T4@5')

    assert dropped(BEFORE, after) == []
    assert restore_dropped(BEFORE, after) == after
    assert shrinkage(BEFORE * 40, after * 40) == ''


def test_a_version_replaced_by_nothing_is_still_dropped():
    from connectonion.rem.page_review import dropped
    after = BEFORE.replace('- T4 is due 2026-11-20. [1]\n', '').replace('- [1] tick:T4@3 — task T4\n', '')

    assert dropped(BEFORE, after) == ['Dropped source id the page had: tick:T4@3']


def test_another_records_version_does_not_excuse_a_loss():
    from connectonion.rem.page_review import dropped
    after = BEFORE.replace('tick:T4@3', 'tick:T9@1')

    assert dropped(BEFORE, after) == ['Dropped source id the page had: tick:T4@3']


def test_unregistered_kinds_keep_exact_ids():
    assert source_versions.superseded({"gmail:aaaaaaaaaaaa"}, {"gmail:bbbbbbbbbbbb"}) == set()
    assert source_versions.record_of("linear:ENG-1@2") is None


def test_the_reader_shows_the_version_cited_not_the_newest(tmp_path):
    from connectonion.rem.reader_model import cited_context
    page = '# Atlas\n\nDue. [1]\n\n## Sources\n- [1] tick:T4@3 — task T4\n'

    contexts = cited_context(tmp_path, [{'text': page}])

    assert contexts['tick:T4@3']['excerpt'] == 'Due 2026-11-20'
