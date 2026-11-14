"""Captured backlog fixtures are invented; no private notebook or model is used."""

import json
import sqlite3
from pathlib import Path

import pytest
from typer.testing import CliRunner

from connectonion.cli.main import app
from connectonion.rem import captured_decisions as captured, decisions, runner
from connectonion.rem.config import default_config, prepare
from connectonion.rem.files import Notebook

WORDS = 'Choose plain files so inspection stays simple.'
SOURCE = 'codex:invented:12'


@pytest.fixture
def book(tmp_path, monkeypatch, rem_clock):
    prepare(tmp_path)
    monkeypatch.setattr(runner, 'ready', lambda config: ('', ''))
    return Notebook(tmp_path)


def project(book, lines):
    book.write('projects/storage.md', '# Storage\n\n## Key decisions\n' + '\n'.join(lines)
               + f'\n\n## Sources\n- [1] {SOURCE}\n')


def session(book, *, words=WORDS, turns=None):
    turns = turns or [('09:15', WORDS, SOURCE)]
    book.write('sessions/storage.md', '# Storage\n\n## Facts\n- Agent: Codex\n'
               + f'\n## Decisions\n- “{words}” (09:15)\n\n## What you typed\n'
               + '\n'.join(f'### {stamp}\n> {text}\n' for stamp, text, _ in turns)
               + '\n## Sources\n' + '\n'.join(f'- {source}' for _, _, source in turns) + '\n')


def test_only_bound_quotes_are_counted_and_offered(book):
    project(book, ['- Prefer readable storage. [1]', f'- “{WORDS}” [1]',
                   '- “An unbound choice.” [9]', '- Unknown'])
    assert captured.pending_count(book) == 1
    packet = captured.material(book)
    assert len(packet) == 1 and WORDS in packet[0]['text']
    assert 'Prefer readable' not in packet[0]['text']
    assert 'unbound choice' not in packet[0]['text']
    assert '- Unknown' not in packet[0]['text']
    assert decisions.status(book.root)['skipped'] == {'no_quote': 2, 'no_source': 1, 'not_owner': 0}


def test_no_quote_backlog_never_calls_model_and_is_counted_once(book, monkeypatch):
    project(book, ['- Prefer readable storage. [1]', '- Keep the choice open. [1]'])
    monkeypatch.setattr(runner, 'run_stage', lambda *a, **kw: pytest.fail('unsupported model turn'))
    for _ in range(2):
        report = decisions.write(book.root)
        assert report['rounds'] == [] and report['left'] == 0
        assert report['skipped'] == {'no_quote': 2, 'no_source': 0, 'not_owner': 0}


@pytest.mark.parametrize('role,text', [('user', 'Keep the choice open.'), ('assistant', WORDS)])
def test_known_contradicted_owner_capture_does_not_count_as_waiting(book, monkeypatch, role, text):
    project(book, [f'- “{WORDS}” [1]'])
    original = book.root / '.state/original.jsonl'
    original.write_text(json.dumps({'source': SOURCE, 'role': role, 'text': text}) + '\n')
    with sqlite3.connect(book.root / '.state/rem.db') as db:
        db.execute('create table messages (id text, source text, sender text, body_path text, body_line integer)')
        db.execute('insert into messages values (?, ?, ?, ?, ?)',
                   (SOURCE, 'codex', '', 'original.jsonl', 1))
    monkeypatch.setattr(runner, 'run_stage', lambda *a, **kw: pytest.fail('contradicted owner capture'))
    assert captured.pending_count(book) == 0
    assert captured.material(book) == []
    assert decisions.write(book.root)['skipped']['not_owner'] == 1


def test_legacy_session_packet_supplies_copyable_source_and_passes_review(book):
    session(book)
    items = captured.material(book)
    assert items[0]['sources'] == [SOURCE]
    assert f'“{WORDS}” [1]' in items[0]['text']
    assert f'- [1] {SOURCE}' in items[0]['text']
    task = runner.prepare(book, items, default_config(), stage='abstract',
                          directory=book.root / '.state/tasks/eligible', native=True)
    Notebook(Path(task['task_root'])).write('decisions/storage.md',
        f'# Storage\n\n“{WORDS}” [1]\n\n## Sources\n- [1] {SOURCE}\n')
    assert runner.check(task, {}, native=True) == []
    assert SOURCE in book.read('decisions/storage.md')
    assert f'“{WORDS}” (09:15)' in book.read('sessions/storage.md')  # Evidence stays untouched.


@pytest.mark.parametrize('turns,words', [
    ([('09:15', 'Leave the question open.', SOURCE)], WORDS),
    ([('09:15', WORDS, SOURCE), ('09:15', WORDS, 'codex:invented:13')], WORDS),
    ([('09:15', WORDS, SOURCE)], WORDS + ' Add an invented reason.'),
])
def test_legacy_session_missing_ambiguous_or_expanded_quote_is_not_offered(book, turns, words):
    session(book, turns=turns, words=words)
    assert captured.pending_count(book) == 0
    assert captured.material(book) == []


def test_session_clock_disambiguates_repeated_owner_words(book):
    session(book, turns=[('09:14', WORDS, 'codex:invented:11'), ('09:15', WORDS, SOURCE)])
    items = captured.material(book)
    assert items[0]['sources'] == [SOURCE]
    assert 'codex:invented:11' not in items[0]['text']


def test_capacity_counts_eligible_lines_and_keeps_original_cursor(book):
    lines = [line for i in range(23) for line in
             [f'- Summary {i}. [1]', f'- “Choose inspection variant {i}.” [1]']]
    project(book, lines)
    items = captured.material(book)
    assert sum(len(captured._quote_bindings(i['text'])) for i in items) == 20
    captured.remember_offered(book.root, items)
    assert captured.pending_count(book) == 3
    assert decisions.status(book.root)['skipped']['no_quote'] == 23
    second = captured.material(book)
    assert 'variant 20.' in second[0]['text'] and 'variant 19.' not in second[0]['text']
    captured.remember_offered(book.root, second)
    assert captured.pending_count(book) == 0


def test_small_packet_never_splits_a_quote_into_unusable_fragments(book):
    project(book, [f'- “{WORDS * 100}” [1]'])
    config = default_config()
    config['limits']['input_chars_per_batch'] = 650
    assert captured.material(book, config) == []
    assert captured.pending_count(book) == 1


def test_cli_explains_eligibility_and_reports_skips_once(book):
    project(book, ['- Prefer readable storage. [1]', f'- “{WORDS}” [1]'])
    args = ['rem', '--root', str(book.root), 'decisions']
    result = CliRunner().invoke(app, args)
    assert result.exit_code == 0, result.output
    assert 'Decisions waiting: 1' in result.output
    assert '1 no quote captured' in result.output
    data = CliRunner().invoke(app, ['rem', '--root', str(book.root), '--json', 'decisions'])
    assert json.loads(data.output)['data']['skipped'] == {'no_quote': 1, 'no_source': 0, 'not_owner': 0}


def test_prompt_makes_cap_optional_and_requires_copying_supplied_definitions(book):
    project(book, [f'- “{WORDS}” [1]'])
    task = runner.prepare(book, captured.material(book), default_config(), stage='abstract',
                          directory=book.root / '.state/tasks/prompt', native=True)
    assert 'This is a ceiling, not a target' in task['prompt']
    assert 'Skip any line without a bound verbatim quote' in task['prompt']
    assert 'Copy the supplied source definition' in task['prompt']
    assert 'do not paraphrase a line into a quote' in task['prompt']
