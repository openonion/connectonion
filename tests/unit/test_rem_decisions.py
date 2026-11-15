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
    assert 'Decision pages: 1 · Principle pages: 1 · Captured lines waiting: 41' in result.output
    assert result.output.rstrip().endswith(f'Next: co rem --root {book.root} abstract')
    assert model[0] == []
    assert not state_path(book.root, 'abstract-offered.json').exists()


def test_manual_decisions_drains_several_rounds_and_reports_each(book, model):
    backlog(book, 45)
    result = invoke(book, 'abstract')
    assert result.exit_code == 0, result.output
    assert len(model[0]) == 3
    assert len(book.list('decisions')) == 45
    assert 'Round 1: 20 captured lines read · 20 pages written · 0 pages refused' in result.output
    assert 'Round 3: 5 captured lines read · 5 pages written · 0 pages refused' in result.output
    assert 'Done: 3 rounds · 45 pages written · 0 pages refused · 0 slices set aside for a later retry · 0 captured lines left' in result.output
    assert result.output.rstrip().endswith(f'Next: co rem --root {book.root} list decisions')
    runs = [read_json(path, {}) for path in state_path(book.root, 'runs').glob('*.json')]
    assert len(runs) == 3 and all(run['outcome'] == 'completed' for run in runs)
    assert not state_path(book.root, 'abstract-night.json').exists()
    again = invoke(book, 'abstract')
    assert again.exit_code == 0 and len(model[0]) == 3
    assert 'Done: 0 rounds · 0 pages written · 0 pages refused · 0 slices set aside for a later retry · 0 captured lines left' in again.output


@pytest.mark.parametrize('success_first', [False, True])
def test_manual_stops_after_two_empty_rounds_with_correct_exit(book, model, success_first):
    backlog(book, 65)
    model[1].extend(['good', 'empty', 'empty'] if success_first else ['empty', 'empty'])
    result = invoke(book, 'abstract')
    assert result.exit_code == (0 if success_first else 1), result.output
    assert len(model[0]) == (3 if success_first else 2)
    number = 3 if success_first else 2
    left = 45 if success_first else 65
    assert f'Round {number}: 20 captured lines read · 0 pages written · 0 pages refused' in result.output
    assert f'2 slices set aside for a later retry · stopped:' in result.output
    assert f'{left} captured lines left' in result.output
    assert 'two empty rounds in a row' in result.output
    offered = read_json(state_path(book.root, 'abstract-offered.json'), {})
    assert len(offered['sessions/backlog.md']['failures']) == 40
    assert len({night for nights in offered['sessions/backlog.md']['failures'].values() for night in nights}) == 2
    assert model[0][-1] != model[0][-2]


def test_manual_empty_then_success_keeps_failed_slice_for_retry(book, model):
    backlog(book, 45)
    model[1].extend(['empty', 'good', 'good'])
    result = invoke(book, 'abstract')
    assert result.exit_code == 0, result.output
    assert len(model[0]) == 3 and len(book.list('decisions')) == 25
    assert '1 slice set aside for a later retry' in result.output
    assert '20 captured lines left' in result.output
    retry = invoke(book, 'abstract')
    assert retry.exit_code == 0, retry.output
    assert len(model[0]) == 4 and model[0][0] == model[0][-1]
    assert len(book.list('decisions')) == 45


def test_manual_success_resets_empty_streak(book, model):
    backlog(book, 100)
    model[1].extend(['empty', 'good', 'empty', 'good', 'good'])
    result = invoke(book, 'abstract')
    assert result.exit_code == 0, result.output
    assert len(model[0]) == 5 and len(book.list('decisions')) == 60


def test_manual_failure_counts_once_per_run_and_releases_on_third(book, model):
    backlog(book, 20)
    model[1].extend(['invalid'] * 3)
    for attempt in range(3):
        result = invoke(book, 'abstract')
        assert result.exit_code == 1, result.output
        assert len(model[0]) == attempt + 1
    assert '0 slices set aside for a later retry' in result.output
    assert invoke(book, 'abstract').exit_code == 0
    assert len(model[0]) == 3
    state = read_json(state_path(book.root, 'abstract-offered.json'), {})['sessions/backlog.md']
    assert len(state['given_up'][0]['nights']) == 3


def test_manual_round_limit_is_independent_of_night_cap(book, model):
    backlog(book, 65)
    marker = {'day': '2026-09-07', 'rounds': 6, 'stopped': True}
    write_json(state_path(book.root, 'abstract-night.json'), marker)
    result = invoke(book, 'abstract', '--rounds', '2')
    assert result.exit_code == 0, result.output
    assert len(model[0]) == 2
    assert 'Done: 2 rounds · 40 pages written · 0 pages refused · 0 slices set aside for a later retry · 25 captured lines left' in result.output
    assert read_json(state_path(book.root, 'abstract-night.json'), {}) == marker


def test_manual_cap_after_one_empty_does_not_report_two_empty_stop(book, model):
    backlog(book, 65)
    model[1].extend(['good', 'empty'])
    result = invoke(book, 'abstract', '--rounds', '2')
    assert result.exit_code == 0, result.output
    assert len(model[0]) == 2 and '1 slice set aside for a later retry' in result.output
    assert 'two empty' not in result.output and 'stopped:' not in result.output


@pytest.mark.parametrize('night_first', [True, False])
def test_manual_and_night_share_the_same_queue(book, model, night_first):
    backlog(book, 40)
    config = default_config()
    config['limits']['abstract_rounds_per_night'] = 1
    if not night_first:
        assert invoke(book, 'abstract', '--rounds', '1').exit_code == 0
    task = native_round.prepare_abstract(book.root, {'phase': 'daily-update'}, config, book.root / 'night')
    assert task is not None
    prepared = task['task']
    first = 0 if night_first else 20
    assert f'“Choice {first}.”' in prepared['items'][0]['text']
    output = Notebook(Path(prepared['task_root']))
    records = []
    for number in range(first, first + 20):
        record = f'decisions/night-{number}.md'
        output.write(record, page(f'Choice {number}.'))
        records.append(record)
    runner.check(prepared, {}, native=True)
    task.update(directory=prepared['directory'], run={'id': 'night', 'quota': {'after': {}}})
    native._log(book.root, task, 'completed', changed=records)
    if night_first:
        result = invoke(book, 'abstract')
        assert result.exit_code == 0, result.output
        assert len(model[0]) == 1 and '“Choice 20.”' in model[0][0][0]['text']
    else:
        assert invoke(book, 'abstract').exit_code == 0
        assert len(model[0]) == 1


def test_manual_partial_refusals_are_printed_and_recorded(book, model):
    backlog(book, 2)
    model[1].append('partial')
    result = invoke(book, 'abstract')
    assert result.exit_code == 0, result.output
    assert 'Round 1: 2 captured lines read · 2 pages written · 1 pages refused' in result.output
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
    result = invoke(book, 'abstract')
    assert result.exit_code == 1, result.output
    assert reason in result.output
    assert book.list('decisions') == [] and not book.exists('people/other.md')
    failures = read_json(state_path(book.root, 'abstract-offered.json'), {})['sessions/backlog.md']['failures']
    assert len(failures) == 20 and all(len(nights) == 1 for nights in failures.values())
    assert len(model[0]) == 1


def test_manual_crash_keeps_material_pending(book, model):
    backlog(book, 3)
    model[1].append('crash')
    result = invoke(book, 'abstract')
    assert result.exit_code == 130, result.output
    assert read_json(state_path(book.root, 'abstract-offered.json'), {}) == {}
    assert invoke(book, 'abstract').exit_code == 0
    assert model[0][0] == model[0][1]


def test_manual_interrupt_after_progress_names_the_pages_kept(book, model):
    backlog(book, 25)
    model[1].extend(['good', 'crash'])
    result = invoke(book, 'abstract')
    assert result.exit_code == 130, result.output
    assert 'Stopped: 20 pages written before the stop' in result.output
    assert 'decisions/choice-0.md' in result.output
    assert len(book.list('decisions')) == 20


def test_manual_run_records_the_selected_abstract_model(book, model):
    from connectonion.rem.inquiry import set_route
    backlog(book, 2)
    set_route(book.root, 'abstract', 'coai', 'co/fixture')
    result = invoke(book, 'abstract')
    assert result.exit_code == 0, result.output
    run = read_json(next(state_path(book.root, 'runs').glob('*.json')), {})
    assert run['harness'] == 'coai' and run['model'] == 'co/fixture'


def test_abstract_is_the_real_stage_command(book, model):
    backlog(book, 45)
    result = invoke(book, 'abstract', '--rounds', '2')
    assert result.exit_code == 0, result.output
    assert 'compatibility alias' not in result.output and 'is now' not in result.output
    assert len(model[0]) == 2


def test_decisions_json_keeps_per_round_results(book, model):
    backlog(book, 2)
    result = invoke(book, 'abstract', json_out=True)
    assert result.exit_code == 0, result.output
    value = json.loads(result.output)
    assert value['ok'] and value['data']['left'] == 0
    assert value['data']['rounds'][0]['read'] == 2


@pytest.mark.parametrize('value', ['0', '-1'])
def test_round_limit_must_be_positive(book, model, value):
    result = invoke(book, 'abstract', '--rounds', value)
    assert result.exit_code == 2
    assert model[0] == []


def test_decisions_are_discoverable_and_help_teaches_the_workflow():
    from connectonion.cli.audit import listed_commands
    main = CliRunner().invoke(app, ['rem', '--help'])
    assert 'decisions' in listed_commands(main.output)
    group = CliRunner().invoke(app, ['rem', 'decisions', '--help'])
    assert group.exit_code == 0 and 'write' not in listed_commands(group.output)
    help_page = CliRunner().invoke(app, ['rem', 'abstract', '--help'])
    assert help_page.exit_code == 0, help_page.output
    for text in ['Usage:', 'Example:', 'Output:', 'Effects:', 'Next:', 'Back:', '--rounds',
                 'Calls the model once per round.', 'Writes only under decisions/ and principles/.',
                 'two empty rounds in a row', 'slices set aside for a later retry', 'Speaker unverified.']:
        assert text in help_page.output


def test_verdict_only_rounds_drain_backlog_without_an_empty_stop(book, monkeypatch):
    from connectonion.rem import decisions
    backlog(book, 45)
    calls = []

    def run(workspace, prompt, config, stage, **options):
        items = json.loads(next(workspace.glob('abstract-*/material.json')).read_text())
        ids = re.findall(r'(?m)^\[(d[0-9a-f]{12})\]', '\n'.join(item['text'] for item in items))
        calls.append(ids)
        return {'result': '\n'.join(f'VERDICT {identity} not-a-decision' for identity in ids)}

    monkeypatch.setattr(runner, 'run_task', run)
    result = decisions.write(book.root)
    assert len(calls) == 3 and sum(map(len, calls)) == 45
    assert result['left'] == 0 and result['written'] == 0
    assert result['skipped']['not_decision'] == 45
    assert not result['failed'] and not result['reason']
