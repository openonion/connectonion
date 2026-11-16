"""Only stored originals establish a decision quote's speaker; all data is invented."""

import json
import hashlib
import sqlite3
from pathlib import Path

import pytest

from connectonion.rem import captured_decisions, runner
from connectonion.rem.config import default_config, prepare
from connectonion.rem.files import Notebook, write_json

WORDS = 'Choose plain files for inspection.'
SOURCE = 'codex:invented:12'


def page(source=SOURCE, words=WORDS):
    return f'# Storage\n\n“{words}” [1]\n\n## Sources\n- [1] {source}\n'


@pytest.fixture
def book(tmp_path, monkeypatch, rem_clock):
    monkeypatch.setattr(runner, 'ready', lambda config: ('', ''))
    prepare(tmp_path)
    write_json(tmp_path / '.state/map.json', {'owner': {'addresses': ['owner@example.test']}})
    return Notebook(tmp_path)


def original(book, source=SOURCE, *, words=WORDS, role='user', sender='owner@example.test'):
    session = source.startswith(('codex:', 'claude-code:'))
    from connectonion.rem.mail_archive import message_path
    path = (book.root / '.state/original.jsonl' if session else
            message_path(book.root, *source.split(':', 1)))
    if session:
        path.write_text(json.dumps({'source': source, 'text': words, 'role': role}) + '\n')
    else:
        write_json(path, {'provider': source.split(':')[0], 'id': source.split(':', 1)[1],
                          'body': words, 'from': sender})
    with sqlite3.connect(book.root / '.state/rem.db') as db:
        db.execute('create table messages (id text, source text, sender text, body_path text, body_line integer)')
        db.execute('insert into messages values (?, ?, ?, ?, ?)',
                   (source, source.split(':')[0], sender, path.relative_to(book.root / '.state').as_posix(), 1 if session else None))


def promote(book, source=SOURCE, *, extra=''):
    from connectonion.rem.page_review import _mail_digest
    # Captures come from pages already saved with canonical archive citations.
    source = _mail_digest(book.root, source)
    book.write('sessions/storage.md', '# Storage\n\n## Decisions\n- “' + WORDS + f'” [1]\n\n## Sources\n- [1] {source}\n')
    task = runner.prepare(book, captured_decisions.material(book), default_config(), stage='abstract',
                          directory=book.root / '.state/tasks/authorship', native=True)
    Notebook(Path(task['task_root'])).write('decisions/storage.md', page(source) + extra)
    return runner.check(task, {}, native=True)


@pytest.mark.parametrize('source', [SOURCE, 'claude-code:invented:12', 'outlook:invented', 'gmail:invented'])
def test_original_owner_words_pass_without_uncertainty(book, source):
    original(book, source)
    assert promote(book, source) == []
    assert 'Speaker unverified' not in book.read('decisions/storage.md')


def test_retained_owner_session_passes_without_index(book):
    from connectonion.rem.project_material import retain_cited_sessions
    retain_cited_sessions(book.root, [{'source': SOURCE, 'role': 'user', 'text': WORDS}], {SOURCE})
    assert promote(book) == []
    assert 'Speaker unverified' not in book.read('decisions/storage.md')


@pytest.mark.parametrize('source', ['outlook:invented', 'gmail:invented'])
def test_someone_elses_authored_mail_is_refused(book, source):
    original(book, source, sender='colleague@example.test')
    with pytest.raises(runner.RunFailed, match='not authored by the owner'):
        promote(book, source)
    assert book.list('decisions') == []


def test_assistant_original_is_refused_even_when_captured_as_owner(book):
    original(book, role='assistant')
    with pytest.raises(runner.RunFailed, match='not authored by the owner'):
        promote(book)


def test_quote_absent_from_complete_owner_original_is_refused(book):
    original(book, words='Keep the choice open until tomorrow.')
    with pytest.raises(runner.RunFailed, match="not in the owner's cited original"):
        promote(book)


@pytest.mark.parametrize('source', [SOURCE, 'outlook:missing', 'https://example.test/choice',
                                  'file:/invented/notes.md', 'git:/invented:revision:notes.md', 'project-source:invented'])
def test_missing_or_non_personal_original_adds_existing_uncertainties_grammar(book, source):
    assert promote(book, source) == []
    text = book.read('decisions/storage.md')
    assert '\n## Uncertainties\n- Speaker unverified.\n' in text
    assert text.index('## Uncertainties') < text.index('## Sources')


def test_mail_quoted_thread_does_not_inherit_senders_authorship(book):
    source = 'outlook:invented'
    original(book, source, words='A new reply.\n\nOn Tuesday a colleague wrote:\n> ' + WORDS)
    assert promote(book, source) == []
    assert 'Speaker unverified.' in book.read('decisions/storage.md')


def test_uncertainties_marker_does_not_bypass_other_author_refusal(book):
    source = 'gmail:invented'
    original(book, source, sender='colleague@example.test')
    with pytest.raises(runner.RunFailed, match='not authored by the owner'):
        promote(book, source, extra='\n## Uncertainties\n- Speaker unverified.\n')


def test_unverified_marker_is_idempotent_and_preserves_existing_uncertainties(book):
    from connectonion.rem.decision_authorship import review
    text = page().replace('## Sources', '## Uncertainties\n- Revisit the cost.\n\n## Sources')
    first, errors = review(book.root, text)
    second, again = review(book.root, first)
    assert errors == again == []
    assert first == second and first.count('Speaker unverified.') == 1
    assert '- Revisit the cost.' in first


def test_quote_beyond_reader_excerpt_uses_full_retained_original(book):
    from connectonion.rem.project_material import retain_cited_sessions
    retain_cited_sessions(book.root, [{'source': SOURCE, 'role': 'user', 'text': 'Earlier context. ' * 400 + WORDS}], {SOURCE})
    assert promote(book) == []
    assert 'Speaker unverified' not in book.read('decisions/storage.md')


def test_truncated_owner_input_does_not_turn_missing_words_into_a_refusal(book):
    original(book, words='Earlier context.\n[truncated by co rem: 5000 more characters in the source]')
    assert promote(book) == []
    assert 'Speaker unverified.' in book.read('decisions/storage.md')


@pytest.mark.parametrize('sender', ['', 'Owner Display', 'Unknown'])
def test_unknown_mail_sender_is_unverified(book, sender):
    source = 'gmail:invented'
    original(book, source, sender=sender)
    assert promote(book, source) == []
    assert 'Speaker unverified.' in book.read('decisions/storage.md')


def test_legacy_short_mail_id_resolves_the_original_owner_body(book):
    original(book, 'gmail:invented-message')
    source = 'gmail:' + hashlib.sha256(b'invented-message').hexdigest()[:12]
    assert promote(book, source) == []
    assert 'Speaker unverified' not in book.read('decisions/storage.md')


@pytest.mark.parametrize('provider', ['gmail', 'outlook'])
def test_full_mail_id_uses_the_indexed_original(book, provider):
    from connectonion.rem.decision_authorship import review
    source = provider + ':invented-message'
    original(book, source)
    text, errors = review(book.root, page(source))
    assert errors == [] and 'Speaker unverified' not in text


# ------------------------------------------- a page that admits it has no alternative or reason

def decided(sentence):
    return (f'# Storage\n\nPlain files. “{WORDS}” [1] {sentence}\n\n## Why\nPages stay readable.\n\n'
            f'## Sources\n- [1] {SOURCE} — originating page: `sessions/storage.md`.\n')


@pytest.mark.parametrize('sentence', [
    'The rejected alternative is unknown.',
    'No alternative was recorded; the reason is inferred from the wording.',
    'The rationale was not stated in the session.',
    'Reasons are unclear.',
    'An inferred reason: the files are easier to read.',
    'There is no stated alternative.'])
def test_a_decision_page_that_says_its_alternative_or_reason_is_unknown_or_inferred_is_refused(book, sentence):
    """2026-11-16: 15 of 66 new decision pages said so in their own text and all passed review,
    which only asked who spoke the quote."""
    from connectonion.rem.decision_authorship import admitted_gaps
    original(book)
    errors = admitted_gaps(decided(sentence))
    assert len(errors) == 1 and 'VERDICT <line id> not-a-decision' in errors[0] and 'delete this page' in errors[0]
    book.write('sessions/storage.md', '# Storage\n\n## Decisions\n- “' + WORDS + f'” [1]\n\n## Sources\n- [1] {SOURCE}\n')
    task = runner.prepare(book, captured_decisions.material(book), default_config(), stage='abstract',
                          directory=book.root / '.state/tasks/admitted', native=True)
    Notebook(Path(task['task_root'])).write('decisions/storage.md', decided(sentence))
    with pytest.raises(runner.RunFailed, match='not-a-decision'):
        runner.check(task, {}, native=True)
    assert book.list('decisions') == []


@pytest.mark.parametrize('sentence', [
    'SQLite was discussed and not adopted.',
    'The user corrected the reason to inspectability and kept the choice.',
    'SQLite was the alternative; what it would cost at a thousand pages is unknown.',
    'Whether search holds up at scale is unknown. The reason was inspection.'])
def test_a_decision_page_with_its_alternative_and_reason_is_not_refused_for_an_unknown_elsewhere(sentence):
    from connectonion.rem.decision_authorship import admitted_gaps
    assert admitted_gaps(decided(sentence)) == []


def test_the_abstract_skill_gives_the_not_a_decision_verdict_to_an_unknown_alternative_or_reason():
    import re
    from connectonion.rem.decision_authorship import admitted_gaps
    from connectonion.skills_catalog import useful_skills_dir
    text = (useful_skills_dir() / 'rem-abstract/SKILL.md').read_text()
    assert ('If the page would have to say that the alternative or the reason is unknown or inferred, '
            'the verdict is `not-a-decision`') in ' '.join(text.split())
    assert admitted_gaps(re.search(r'(?s)```markdown\n(# Where the notebook.*?)```', text)[1]) == []
