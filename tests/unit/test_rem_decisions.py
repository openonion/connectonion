"""Manual decision writing uses the night's queue and the existing model boundary."""

import json
import re
from pathlib import Path

import pytest
from typer.testing import CliRunner

from connectonion.cli.main import app
from connectonion.rem import native, native_round, runner
from connectonion.rem.config import default_config, prepare
from connectonion.rem.files import Notebook, read_json, state_path, write_json

pytestmark = pytest.mark.usefixtures('rem_clock')
SOURCE = 'codex:fixture:7'


@pytest.fixture
def book(tmp_path):
    prepare(tmp_path)
    return Notebook(tmp_path)


def backlog(book, count):
    book.write('sessions/backlog.md', '# Backlog\n\n## Decisions\n'
               + '\n'.join(f'- “Choice {i}.” [1]' for i in range(count))
               + f'\n\n## Sources\n- [1] {SOURCE}\n')


def page(words, source=SOURCE):
    return f'# A choice\n\n“{words}” [1]\n\n## Sources\n- [1] {source}\n'


@pytest.fixture
def model(monkeypatch):
    calls, modes = [], []

    def run(workspace, prompt, config, stage, **options):
        packet = next(workspace.glob('abstract-*/material.json'))
        items = json.loads(packet.read_text())
        calls.append(items)
        output = Notebook(packet.parent / 'notebook')
        mode = modes.pop(0) if modes else 'good'
        if mode == 'crash':
            raise KeyboardInterrupt
        if mode == 'empty':
            return {'result': 'No change', 'usage': {'input_tokens': 10}}
        for item in items:
            for words in re.findall('“([^”]+)”', item['text']):
                output.write(f'decisions/choice-{words.split()[1].strip(".")}.md', page(words))
        if mode == 'partial':
            output.write('decisions/proposal.md', '# Assistant proposal\n\nUse a database.\n')
        if mode == 'invalid':
            for record in output.list('decisions'):
                output.path(record).unlink()
            output.write('decisions/proposal.md', '# Assistant proposal\n\nUse a database.\n')
        if mode == 'scope':
            output.write('people/other.md', '# Outside scope\n')
        if mode == 'limit':
            output.write('decisions/extra.md', page('Choice 0.'))
        if mode == 'invented':
            for record in output.list('decisions'):
                output.write(record, page('An invented owner quote.'))
        return {'result': 'Captured choices', 'usage': {'input_tokens': 10}}

    monkeypatch.setattr(runner, 'run_task', run)
    return calls, modes


def invoke(book, *args, json_out=False):
    return CliRunner().invoke(app, ['rem', '--root', str(book.root),
                                   *(['--json'] if json_out else []), *args])


def test_decisions_status_counts_pages_and_pending_without_model(book, model):
    backlog(book, 41)
    book.write('decisions/existing.md', page('Choice 0.'))
    book.write('principles/existing.md', '# A principle\n')
    result = invoke(book, 'decisions')
    assert result.exit_code == 0, result.output
    assert 'Decision pages: 1 · Principle pages: 1 · Decisions waiting: 41' in result.output
    assert result.output.rstrip().endswith(f'Next: co rem --root {book.root} decisions write')
    assert model[0] == []
    assert not state_path(book.root, 'abstract-offered.json').exists()


def test_manual_decisions_drains_several_rounds_and_reports_each(book, model):
    backlog(book, 45)
    result = invoke(book, 'decisions', 'write')
    assert result.exit_code == 0, result.output
    assert len(model[0]) == 3
    assert len(book.list('decisions')) == 45
    assert 'Round 1: 20 decisions read · 20 pages written · 0 refused' in result.output
    assert 'Round 3: 5 decisions read · 5 pages written · 0 refused' in result.output
    assert 'Done: 3 rounds · 45 pages written · 0 refused · 0 decisions left' in result.output
    assert result.output.rstrip().endswith(f'Next: co rem --root {book.root} list decisions')
    runs = [read_json(path, {}) for path in state_path(book.root, 'runs').glob('*.json')]
    assert len(runs) == 3 and all(run['outcome'] == 'completed' for run in runs)
    assert not state_path(book.root, 'abstract-night.json').exists()
    again = invoke(book, 'decisions', 'write')
    assert again.exit_code == 0 and len(model[0]) == 3
    assert 'Done: 0 rounds · 0 pages written · 0 refused · 0 decisions left' in again.output


@pytest.mark.parametrize('success_first', [False, True])
def test_manual_stops_when_round_writes_nothing_with_correct_exit(book, model, success_first):
    backlog(book, 45)
    model[1].extend(['good', 'empty'] if success_first else ['empty'])
    result = invoke(book, 'decisions', 'write')
    assert result.exit_code == (0 if success_first else 1), result.output
    assert len(model[0]) == (2 if success_first else 1)
    number = 2 if success_first else 1
    left = 25 if success_first else 45
    assert f'Round {number}: 20 decisions read · 0 pages written · 0 refused' in result.output
    assert f'stopped: round {number} wrote no page · {left} decisions left' in result.output
    assert result.output.rstrip().endswith('Reason: Abstract wrote no passing pages')
    offered = read_json(state_path(book.root, 'abstract-offered.json'), {})
    assert 'failures' not in offered.get('sessions/backlog.md', {})
    if not success_first:
        assert offered == {}


def test_manual_round_limit_is_independent_of_night_cap(book, model):
    backlog(book, 65)
    marker = {'day': '2026-09-07', 'rounds': 6, 'stopped': True}
    write_json(state_path(book.root, 'abstract-night.json'), marker)
    result = invoke(book, 'decisions', 'write', '--rounds', '2')
    assert result.exit_code == 0, result.output
    assert len(model[0]) == 2
    assert 'Done: 2 rounds · 40 pages written · 0 refused · 25 decisions left' in result.output
    assert read_json(state_path(book.root, 'abstract-night.json'), {}) == marker


@pytest.mark.parametrize('night_first', [True, False])
def test_manual_and_night_share_the_same_queue(book, model, night_first):
    backlog(book, 40)
    config = default_config()
    config['limits']['abstract_rounds_per_night'] = 1
    if not night_first:
        assert invoke(book, 'decisions', 'write', '--rounds', '1').exit_code == 0
    task = native_round.prepare_abstract(book.root, {'phase': 'daily-update'}, config, book.root / 'night')
    assert task is not None
    prepared = task['task']
    first = 0 if night_first else 20
    assert f'“Choice {first}.”' in prepared['items'][0]['text']
    output = Notebook(Path(prepared['task_root']))
    output.write(f'decisions/night-{first}.md', page(f'Choice {first}.'))
    runner.check(prepared, {}, native=True)
    task.update(directory=prepared['directory'], run={'id': 'night', 'quota': {'after': {}}})
    native._log(book.root, task, 'completed', changed=[f'decisions/night-{first}.md'])
    if night_first:
        result = invoke(book, 'decisions', 'write')
        assert result.exit_code == 0, result.output
        assert len(model[0]) == 1 and '“Choice 20.”' in model[0][0][0]['text']
    else:
        assert invoke(book, 'decisions', 'write').exit_code == 0
        assert len(model[0]) == 1


def test_manual_partial_refusals_are_printed_and_recorded(book, model):
    backlog(book, 2)
    model[1].append('partial')
    result = invoke(book, 'decisions', 'write')
    assert result.exit_code == 0, result.output
    assert 'Round 1: 2 decisions read · 2 pages written · 1 refused' in result.output
    assert 'refused decisions/proposal.md:' in result.output
    assert not book.exists('decisions/proposal.md')
    run = read_json(next(state_path(book.root, 'runs').glob('*.json')), {})
    assert run['refused'][0]['record'] == 'decisions/proposal.md'


@pytest.mark.parametrize('mode,reason', [('invalid', "owner's words"),
                                        ('scope', 'only decisions/ and principles/'),
                                        ('limit', 'at most 20'), ('invented', "owner's words")])
def test_manual_applies_nightly_page_checks_and_preserves_queue(book, model, mode, reason):
    backlog(book, 20)
    model[1].append(mode)
    result = invoke(book, 'decisions', 'write')
    assert result.exit_code == 1, result.output
    assert reason in result.output
    assert book.list('decisions') == [] and not book.exists('people/other.md')
    assert read_json(state_path(book.root, 'abstract-offered.json'), {}) == {}
    assert len(model[0]) == 1


def test_manual_crash_keeps_material_pending(book, model):
    backlog(book, 3)
    model[1].append('crash')
    result = invoke(book, 'decisions', 'write')
    assert result.exit_code == 130, result.output
    assert read_json(state_path(book.root, 'abstract-offered.json'), {}) == {}
    assert invoke(book, 'decisions', 'write').exit_code == 0
    assert model[0][0] == model[0][1]


def test_manual_interrupt_after_progress_names_the_pages_kept(book, model):
    backlog(book, 25)
    model[1].extend(['good', 'crash'])
    result = invoke(book, 'decisions', 'write')
    assert result.exit_code == 130, result.output
    assert 'Stopped: 20 pages written before the stop' in result.output
    assert 'decisions/choice-0.md' in result.output
    assert len(book.list('decisions')) == 20


def test_manual_run_records_the_selected_abstract_model(book, model):
    from connectonion.rem.inquiry import set_route
    backlog(book, 2)
    set_route(book.root, 'abstract', 'coai', 'co/fixture')
    result = invoke(book, 'decisions', 'write')
    assert result.exit_code == 0, result.output
    run = read_json(next(state_path(book.root, 'runs').glob('*.json')), {})
    assert run['harness'] == 'coai' and run['model'] == 'co/fixture'


def test_abstract_is_a_working_alias_for_decisions_write(book, model):
    backlog(book, 45)
    result = invoke(book, 'abstract', '--rounds', '2')
    assert result.exit_code == 0, result.output
    assert 'decisions write' in result.output and 'compatibility alias' in result.output
    assert len(model[0]) == 2


def test_decisions_json_keeps_per_round_results(book, model):
    backlog(book, 2)
    result = invoke(book, 'decisions', 'write', json_out=True)
    assert result.exit_code == 0, result.output
    value = json.loads(result.output)
    assert value['ok'] and value['data']['left'] == 0
    assert value['data']['rounds'][0]['read'] == 2


@pytest.mark.parametrize('value', ['0', '-1'])
def test_round_limit_must_be_positive(book, model, value):
    result = invoke(book, 'decisions', 'write', '--rounds', value)
    assert result.exit_code == 2
    assert model[0] == []


def test_decisions_are_discoverable_and_help_teaches_the_workflow():
    from connectonion.cli.audit import listed_commands
    main = CliRunner().invoke(app, ['rem', '--help'])
    assert 'decisions' in listed_commands(main.output)
    group = CliRunner().invoke(app, ['rem', 'decisions', '--help'])
    assert group.exit_code == 0 and 'write' in listed_commands(group.output)
    help_page = CliRunner().invoke(app, ['rem', 'decisions', 'write', '--help'])
    assert help_page.exit_code == 0, help_page.output
    for text in ['Usage:', 'Example:', 'Output:', 'Effects:', 'Next:', 'Back:', '--rounds',
                 'Calls the model once per round.', 'Writes only under decisions/ and principles/.']:
        assert text in help_page.output
