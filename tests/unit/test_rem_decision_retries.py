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
    assert first['lines']['written'] == first['lines']['refused'] == first['lines']['no_answer'] == 1
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


def verdict_model(monkeypatch, reply=None, *, pages=(), report=None):
    calls = []

    def run(workspace, prompt, config, stage, **options):
        packet = next(workspace.glob('abstract-*/material.json'))
        items = json.loads(packet.read_text())
        lines = [(match[1], match[2]) for item in items
                 for match in re.finditer(r'(?m)^\[(d[0-9a-f]{12})\] (.+)$', item['text'])]
        assert lines, 'Every offered line needs its stable ID in the packet'
        calls.append(lines)
        output = Notebook(packet.parent / 'notebook')
        for record, text in pages:
            output.write(record, text)
        if report is not None:
            (packet.parent / 'report.md').write_text(report(lines), encoding='utf-8')
        final = reply(lines) if reply else f'[Report and verdicts]({packet.parent.name}/report.md)'
        return {'result': final, 'usage': {}}

    monkeypatch.setattr(runner, 'run_task', run)
    return calls


def test_decision_verdicts_only_in_report_file_survive_link_only_reply(book, monkeypatch):
    verdict_model(monkeypatch, report=lambda lines: '\n'.join(
        f'VERDICT {line_id} not-a-decision' for line_id, _ in lines))
    result = decisions.write(book.root, rounds=1)
    assert result['lines']['not_decision'] == 3 and result['left'] == 0
    assert result['lines']['no_answer'] == 0 and result['set_aside'] == 0
    folder = next(state_path(book.root, 'tasks').glob('abstract-*'))
    saved = read_json(folder / 'result.json', {})
    assert saved['report'] == result['rounds'][0]['report']
    assert saved['report'].startswith(f'[Report and verdicts]({folder.name}/report.md)\n\n')
    assert saved['report'].count('VERDICT ') == 3
    assert not (folder / 'report.md').exists()  # Collected before private task copies are scrubbed.
    assert decisions.status(book.root)['waiting'] == 0


def test_decision_verdicts_union_report_file_and_final_message(book, monkeypatch):
    verdict_model(monkeypatch, lambda lines: f'VERDICT {lines[0][0]} not-a-decision', report=lambda lines:
        f'VERDICT {lines[0][0]} not-a-decision\nVERDICT {lines[1][0]} not-a-decision\n'
        'VERDICT d000000000000 not-a-decision')
    result = decisions.write(book.root, rounds=1)
    assert result['lines']['not_decision'] == 2
    assert result['lines']['no_answer'] == 1 and result['left'] == 1


def test_decision_merge_in_report_file_requires_passing_page(book, monkeypatch):
    verdict_model(monkeypatch, report=lambda lines: '\n'.join(
        f'VERDICT {line_id} merged decisions/zero.md' for line_id, _ in lines[1:]),
        pages=[('decisions/zero.md', page(0))])
    result = decisions.write(book.root, rounds=1)
    assert result['lines']['written'] == 1 and result['lines']['merged'] == 2
    assert result['left'] == 0


@pytest.mark.parametrize('target', ['missing', 'existing', 'refused'])
def test_decision_report_file_cannot_merge_into_unpassed_page(book, monkeypatch, target):
    if target == 'existing':
        book.write('decisions/target.md', page('unoffered'))
    verdict_model(monkeypatch, report=lambda lines: '\n'.join(
        f'VERDICT {line_id} merged decisions/target.md' for line_id, _ in lines),
        pages=[('decisions/target.md', page(1, broken=True))] if target == 'refused' else [])
    result = decisions.write(book.root, rounds=1)
    assert result['lines']['merged'] == 0 and result['left'] == 3
    assert result['lines']['refused' if target == 'refused' else 'no_answer'] == 3
    assert 'VERDICT ' in result['rounds'][0]['report']  # Failed checks retain the collected report too.


def test_decision_conflicting_verdicts_across_file_and_message_stay_unanswered(book, monkeypatch):
    verdict_model(monkeypatch, lambda lines: '\n'.join(
        f'VERDICT {line_id} not-a-decision' for line_id, _ in lines), report=lambda lines: '\n'.join(
        f'VERDICT {line_id} merged decisions/missing.md' for line_id, _ in lines))
    result = decisions.write(book.root, rounds=1)
    assert result['lines']['no_answer'] == 3 and result['left'] == 3
    assert result['skipped']['not_decision'] == 0


def test_decision_link_without_report_file_is_no_answer(book, monkeypatch):
    verdict_model(monkeypatch)
    result = decisions.write(book.root, rounds=1)
    assert result['lines']['no_answer'] == 3 and result['left'] == 3
    assert result['skipped']['not_decision'] == 0


def test_decision_written_counts_the_quoted_line_only(book, monkeypatch):
    verdict_model(monkeypatch, lambda lines: '', pages=[('decisions/zero.md', page(0))])
    result = decisions.write(book.root, rounds=1)
    assert result['lines']['written'] == 1
    assert result['lines']['no_answer'] == 2
    assert result['left'] == 2
    assert decisions.status(book.root)['lines'] == result['lines']


def test_decision_merged_names_a_passing_page_and_never_retries(book, monkeypatch):
    calls = verdict_model(monkeypatch, lambda lines: '\n'.join(
        f'VERDICT {line_id} merged decisions/zero.md' for line_id, _ in lines[1:]),
        pages=[('decisions/zero.md', page(0))])
    result = decisions.write(book.root)
    assert result['lines']['written'] == 1 and result['lines']['merged'] == 2
    assert result['left'] == 0 and result['set_aside'] == 0
    assert decisions.status(book.root)['to_retry'] == 0
    assert decisions.write(book.root)['rounds'] == [] and len(calls) == 1
    cli = CliRunner().invoke(app, ['rem', '--root', str(book.root), 'decisions'])
    assert '2 merged' in cli.output


def test_not_a_decision_finishes_without_pages_or_retry_and_counts_skipped(book, monkeypatch):
    calls = verdict_model(monkeypatch, lambda lines: '\n'.join(
        f'VERDICT {line_id} not-a-decision' for line_id, _ in lines))
    cli = CliRunner().invoke(app, ['rem', '--root', str(book.root), 'decisions', 'write'])
    assert cli.exit_code == 0, cli.output
    assert '3 not a decision' in cli.output and '0 captured lines left' in cli.output
    assert 'Round 1:' in cli.output and 'Skipped: 3 not a decision' in cli.output.split('Done:')[0]
    assert 'stopped:' not in cli.output
    status = decisions.status(book.root)
    assert status['waiting'] == 0 and status['to_retry'] == 0
    assert status['skipped']['not_decision'] == 3
    assert decisions.write(book.root)['rounds'] == [] and len(calls) == 1


def test_refused_merge_keeps_check_reason_and_gives_up_on_third_try(book, monkeypatch):
    verdict_model(monkeypatch, lambda lines: '\n'.join(
        f'VERDICT {line_id} merged decisions/one.md' for line_id, _ in lines),
        pages=[('decisions/one.md', page(1, broken=True))])
    for attempt in range(3):
        result = decisions.write(book.root, rounds=1)
        assert result['lines']['refused'] == 3
        assert result['left'] == (3 if attempt < 2 else 0)
    assert result['given_up'] == 3
    assert decisions.status(book.root)['to_retry'] == 0
    cli = CliRunner().invoke(app, ['rem', '--root', str(book.root), 'decisions'])
    assert '3 refused' in cli.output and '3 given up' in cli.output
    state = read_json(state_path(book.root, 'abstract-offered.json'), {})['sessions/example.md']
    assert all('Missing or duplicate citation: 1' in row['reason'] for row in state['given_up'])


def test_no_answer_ignores_unoffered_verdicts_and_gives_up_on_third_try(book, monkeypatch):
    calls = verdict_model(monkeypatch, lambda lines: 'VERDICT d000000000000 not-a-decision')
    for attempt in range(3):
        result = decisions.write(book.root, rounds=1)
        assert result['lines']['no_answer'] == 3 and result['lines']['refused'] == 0
        assert result['left'] == (3 if attempt < 2 else 0)
    assert result['given_up'] == 3 and len(calls) == 3
    assert calls[0] == calls[1] == calls[2]
    assert decisions.status(book.root)['skipped']['not_decision'] == 0


def test_old_failures_get_one_more_offer_for_a_verdict_without_losing_history(book, monkeypatch):
    # Produce the pre-verdict on-disk shape, including lines already given up.
    items = captured_decisions.material(book)
    for attempt in range(3):
        captured_decisions.remember_offered(book.root, items, changed=[], night=str(attempt), reason='Old failure')
    path = state_path(book.root, 'abstract-offered.json')
    saved = read_json(path, {})
    for state in saved.values():
        state.pop('verdict_progress', None)
        state.pop('verdicts', None)
    write_json(path, saved)
    original = path.read_bytes()
    assert decisions.status(book.root)['waiting'] == 3
    assert path.read_bytes() == original  # Status migration is read-only.
    calls = verdict_model(monkeypatch, lambda lines: '\n'.join(
        f'VERDICT {line_id} not-a-decision' for line_id, _ in lines))
    result = decisions.write(book.root)
    assert result['left'] == 0 and result['skipped']['not_decision'] == 3
    assert len(calls) == 1 and decisions.write(book.root)['rounds'] == []
    assert read_json(path, {})['sessions/example.md']['given_up'] == saved['sessions/example.md']['given_up']


@pytest.mark.parametrize('target', ['decisions/missing.md', 'principles/existing.md', 'decisions/existing.md'])
def test_merge_requires_a_decision_page_that_passed_this_round(book, monkeypatch, target):
    if 'missing' not in target:
        book.write(target, page(0))
    verdict_model(monkeypatch, lambda lines: '\n'.join(
        f'VERDICT {line_id} merged {target}' for line_id, _ in lines))
    result = decisions.write(book.root, rounds=1)
    assert result['lines']['merged'] == 0
    assert result['left'] == (2 if target == 'decisions/existing.md' else 3)


def test_decision_ids_survive_packet_size_changes(book):
    config = default_config()
    first = captured_decisions.material(book)
    config['limits']['input_chars_per_batch'] = 480
    smaller = captured_decisions.material(book, config)
    ids = lambda items: re.findall(r'(?m)^\[(d[0-9a-f]{12})\]', items[0]['text'])
    assert ids(smaller) and ids(smaller) == ids(first)[:len(ids(smaller))]


def test_abstract_prompt_teaches_verdicts_without_removing_trialled_text(book):
    directory = book.root / 'verdict-prompt'
    prompt = runner.prepare(book, captured_decisions.material(book), default_config(), stage='abstract',
                            directory=directory, native=True)['prompt']
    assert f'Write your report, including the VERDICT lines, to {directory / "report.md"}.' in prompt
    assert 'Repeat those lines in your final message' in prompt
    prompt += runner.instructions('abstract')
    for text in ['Was an alternative rejected?', 'Expect to discard most of what you read.',
                 'several artifacts collapse into one page', 'VERDICT', 'not-a-decision', 'merged']:
        assert text in prompt


def test_not_decision_verdict_cannot_acknowledge_a_refused_quote(book, monkeypatch):
    verdict_model(monkeypatch, lambda lines: '\n'.join(
        f'VERDICT {line_id} not-a-decision' for line_id, _ in lines),
        pages=[('decisions/one.md', page(1, broken=True))])
    result = decisions.write(book.root, rounds=1)
    assert result['lines']['refused'] == 1
    assert result['skipped']['not_decision'] == 2
    assert result['left'] == 1


def test_conflicting_verdicts_leave_the_line_unanswered(book, monkeypatch):
    verdict_model(monkeypatch, lambda lines: '\n'.join(
        f'VERDICT {line_id} not-a-decision\nVERDICT {line_id} merged decisions/missing.md'
        for line_id, _ in lines))
    result = decisions.write(book.root, rounds=1)
    assert result['lines']['no_answer'] == 3 and result['left'] == 3
    assert result['skipped']['not_decision'] == 0


def test_inexact_quote_is_refused_with_its_check_reason(book, monkeypatch):
    verdict_model(monkeypatch, lambda lines: '', pages=[('decisions/inexact.md', page('invented'))])
    first = decisions.write(book.root, rounds=1)
    assert first['lines']['refused'] == 3 and first['lines']['no_answer'] == 0
    prepared = runner.prepare(book, captured_decisions.material(book), default_config(), stage='abstract',
                              directory=book.root / 'inexact-retry', native=True)
    assert "quote the owner's words exactly as captured" in prepared['prompt']


def test_cli_reports_each_line_state_separately(book, monkeypatch):
    book.write('sessions/example.md', '# Example\n\n## Decisions\n'
               + '\n'.join(f'- “Choice {n}.” [1]' for n in range(5))
               + f'\n\n## Sources\n- [1] {SOURCE}\n')
    verdict_model(monkeypatch, lambda lines:
        f'VERDICT {lines[1][0]} merged decisions/zero.md\nVERDICT {lines[2][0]} not-a-decision',
        pages=[('decisions/zero.md', page(0)), ('decisions/three.md', page(3, broken=True))])
    args = ['rem', '--root', str(book.root), 'decisions']
    result = CliRunner().invoke(app, [*args, 'write', '--rounds', '1'])
    assert result.exit_code == 0, result.output
    status = CliRunner().invoke(app, args)
    for output in (result.output, status.output):
        assert 'Lines: 1 written · 1 merged · 1 refused · 1 no answer' in output
        assert '1 not a decision' in output
    assert '2 captured lines left' in result.output
    assert 'Captured lines waiting: 2 · 2 to retry' in status.output
    pending = str(captured_decisions.material(book))
    assert 'Choice 3.' in pending and 'Choice 4.' in pending
    assert all(f'Choice {number}.' not in pending for number in range(3))
