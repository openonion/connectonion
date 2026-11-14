"""Invented captures reproduce mixed promotion and duplicate link-label refusals."""

import json
import re
from pathlib import Path

import pytest
from typer.testing import CliRunner

from connectonion.cli.main import app
from connectonion.rem import captured_decisions, decisions, native, native_round, runner
from connectonion.rem.config import default_config, prepare
from connectonion.rem.files import Notebook, read_json, state_path, write_json
from connectonion.rem.page_review import validate

SOURCE = 'codex:invented-retry:7'
SHAPE = '- [1] source-id — originating page: `sessions/example.md`'
pytestmark = pytest.mark.usefixtures('rem_clock')


def page(number, *, broken=False, source=SOURCE):
    text = f'# Choice {number}\n\n“Choice {number}.” [1]\n\n## Sources\n- [1] {source}\n'
    return text + ('\nOriginating pages:\n[1]: ../sessions/example.md\n' if broken else '')


@pytest.fixture
def book(tmp_path, monkeypatch):
    prepare(tmp_path)
    monkeypatch.setattr(runner, 'ready', lambda config: ('', ''))
    notebook = Notebook(tmp_path)
    notebook.write('sessions/example.md', '# Example\n\n## Decisions\n'
                   + '\n'.join(f'- “Choice {n}.” [1]' for n in range(3))
                   + f'\n\n## Sources\n- [1] {SOURCE}\n')
    return notebook


@pytest.fixture
def mixed_model(monkeypatch):
    calls = []

    def run(workspace, prompt, config, stage, **options):
        packet = next(workspace.glob('abstract-*/material.json'))
        items = json.loads(packet.read_text())
        calls.append((items, prompt))
        output = Notebook(packet.parent / 'notebook')
        if len(calls) == 1:
            output.write('decisions/zero.md', page(0))
            output.write('decisions/one.md', page(1, broken=True))
        else:
            for item in items:
                for number in re.findall(r'“Choice (\d+)\.”', item['text']):
                    output.write(f'decisions/retry-{number}.md', page(number))
        return {'result': 'Choices', 'usage': {}}

    monkeypatch.setattr(runner, 'run_task', run)
    return calls


def test_mixed_round_keeps_refused_and_unwritten_lines_with_feedback(book, mixed_model):
    first = decisions.write(book.root, rounds=1)
    assert first['written'] == 1 and first['refused'] == 1
    assert first['left'] == 2
    status = decisions.status(book.root)
    assert status['to_retry'] == 2
    cli = CliRunner().invoke(app, ['rem', '--root', str(book.root), 'decisions'])
    assert '2 to retry' in cli.output
    second = decisions.write(book.root)
    assert second['written'] == 2 and second['left'] == 0
    assert len(mixed_model) == 2
    items, prompt = mixed_model[1]
    assert '“Choice 0.”' not in str(items)
    assert 'Missing or duplicate citation: 1' in prompt
    assert 'Citation has no identifiable source: 1' in prompt
    assert decisions.status(book.root)['to_retry'] == 0


def test_partial_round_sets_failures_aside_until_next_manual_run(book, mixed_model):
    result = decisions.write(book.root)
    assert len(mixed_model) == 1
    assert result['left'] == 2 and result['set_aside'] == 1


def test_refused_line_gives_up_after_three_distinct_runs_with_actual_reason(book, monkeypatch):
    calls = []

    def run(workspace, prompt, config, stage, **options):
        packet = next(workspace.glob('abstract-*/material.json'))
        calls.append(json.loads(packet.read_text()))
        output = Notebook(packet.parent / 'notebook')
        if len(calls) == 1:
            output.write('decisions/zero.md', page(0))
            output.write('decisions/two.md', page(2))
        output.write('decisions/one.md', page(1, broken=True))
        return {'result': 'Choices', 'usage': {}}

    monkeypatch.setattr(runner, 'run_task', run)
    for attempt in range(3):
        result = decisions.write(book.root)
        assert len(calls) == attempt + 1
        assert result['left'] == (1 if attempt < 2 else 0)
    saved = read_json(state_path(book.root, 'abstract-offered.json'), {})['sessions/example.md']
    assert len(saved['given_up']) == 1
    assert len(saved['given_up'][0]['nights']) == 3
    assert 'Missing or duplicate citation: 1' in saved['given_up'][0]['reason']
    assert decisions.write(book.root)['rounds'] == []


def test_native_partial_result_preserves_lines_and_does_not_retry_same_night(book, monkeypatch):
    monkeypatch.setattr(native.quota, 'read', lambda *a: {})
    config = default_config()
    task = native_round.prepare_abstract(book.root, {'phase': 'daily-update'}, config, book.root / 'native')
    prepared = task['task']
    output = Notebook(Path(prepared['task_root']))
    output.write('decisions/zero.md', page(0))
    output.write('decisions/one.md', page(1, broken=True))
    refused = runner.check(prepared, {}, native=True)
    task.update(directory=prepared['directory'], run={'id': 'native-retries'})
    native._log(book.root, task, 'completed', changed=['decisions/zero.md'], refused=refused)
    assert captured_decisions.pending_count(book) == 2
    assert native_round.prepare_abstract(book.root, {'phase': 'daily-update'}, config, book.root / 'same-night') is None
    items = captured_decisions.material(book)
    prompt = runner.prepare(book, items, config, stage='abstract', directory=book.root / 'manual', native=True)['prompt']
    assert 'Missing or duplicate citation: 1' in prompt


def test_other_source_with_same_words_does_not_complete_captured_line(book, monkeypatch):
    def run(*args, **kwargs):
        book.write('decisions/unrelated.md', page(0, source='codex:another:9'))
        return {'changed': ['decisions/unrelated.md'], 'refusals': [], 'usage': {}}

    monkeypatch.setattr(runner, 'run_stage', run)
    assert decisions.write(book.root, rounds=1)['left'] == 3


def test_duplicate_origin_link_is_still_refused_with_accepted_shape():
    errors = validate('decisions/one.md', page(1, broken=True), '', [{'source': SOURCE}])
    assert any('Missing or duplicate citation: 1' in error for error in errors)
    assert any('Citation has no identifiable source: 1' in error for error in errors)
    assert any(SHAPE in error and '[n]:' in error for error in errors)


def test_prompt_puts_context_inline_and_forbids_numeric_link_definitions(book):
    prepared = runner.prepare(book, captured_decisions.material(book), default_config(), stage='abstract',
                              directory=book.root / 'prompt', native=True)
    assert SHAPE in prepared['prompt']
    assert 'Do not add [n]: Markdown link definitions' in prepared['prompt']


def test_legacy_partial_receipt_recovers_refused_line_without_resetting_success(book, mixed_model):
    items = captured_decisions.material(book)
    captured_decisions.remember_offered(book.root, items)
    book.write('decisions/zero.md', page(0))
    folder = state_path(book.root, 'tasks/abstract-invented')
    refused = folder / 'refused/decisions/one.md'
    refused.parent.mkdir(parents=True)
    refused.write_text(page(1, broken=True))
    write_json(folder / 'review.json', {'accepted': ['decisions/zero.md'], 'refused': [
        {'record': 'decisions/one.md', 'errors': ['Missing or duplicate citation: 1']}]})
    original = state_path(book.root, 'abstract-offered.json').read_bytes()
    assert decisions.status(book.root)['waiting'] == 1
    assert decisions.status(book.root)['to_retry'] == 1
    assert state_path(book.root, 'abstract-offered.json').read_bytes() == original
    # A repaired canonical page suppresses the stale historical refusal.
    book.write('decisions/one.md', page(1))
    assert decisions.status(book.root)['waiting'] == 0


def test_already_captured_choice_completes_without_a_rewrite(book, monkeypatch):
    book.write('decisions/zero.md', page(0))
    monkeypatch.setattr(runner, 'run_stage', lambda *a, **kw: {'changed': [], 'refusals': []})
    result = decisions.write(book.root, rounds=1)
    assert result['written'] == 0 and result['left'] == 2


def test_refused_update_cannot_complete_line_from_its_old_canonical_page(book, monkeypatch):
    book.write('decisions/zero.md', page(0))
    monkeypatch.setattr(runner, 'run_stage', lambda *a, **kw: {
        'changed': [], 'refusals': [{'record': 'decisions/zero.md', 'errors': ['Missing or duplicate citation: 1']}]})
    result = decisions.write(book.root, rounds=1)
    assert result['left'] == 3


def test_old_packet_cannot_checkpoint_a_changed_capture(book):
    items = captured_decisions.material(book)
    original = book.read('sessions/example.md')
    book.write('sessions/example.md', original.replace('Choice 0.', 'Choice zero, revised.'))
    book.write('decisions/zero.md', page(0))
    captured_decisions.remember_offered(book.root, items, changed=['decisions/zero.md'], night='old-packet')
    assert read_json(state_path(book.root, 'abstract-offered.json'), {}) == {}


def test_line_attempts_survive_a_different_packet_budget(book, monkeypatch):
    monkeypatch.setattr(runner, 'run_stage', lambda *a, **kw: {'changed': [], 'refusals': []})
    decisions.write(book.root, rounds=1)
    config = default_config()
    config['limits']['input_chars_per_batch'] = 480
    items = captured_decisions.material(book, config)
    assert items and 'Choice 0.' in items[0]['text']
    captured_decisions.remember_offered(book.root, items, changed=[], night='second')
    captured_decisions.remember_offered(book.root, items, changed=[], night='second')
    state = read_json(state_path(book.root, 'abstract-offered.json'), {})['sessions/example.md']
    assert not state.get('given_up')
    captured_decisions.remember_offered(book.root, items, changed=[], night='third', reason='Still refused')
    state = read_json(state_path(book.root, 'abstract-offered.json'), {})['sessions/example.md']
    assert state['given_up'] and all(len(row['nights']) == 3 for row in state['given_up'])
