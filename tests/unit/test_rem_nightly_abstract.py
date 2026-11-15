"""The night lifts captured choices without reopening sources or other pages."""
from pathlib import Path
import json
import re

import pytest

from connectonion.rem import native_round, runner, service
from connectonion.rem.config import default_config, prepare
from connectonion.rem.files import Notebook, read_json, state_path, write_json
from connectonion.rem.page_review import validate

pytestmark = pytest.mark.usefixtures('rem_clock')

SOURCE = 'codex:fixture:7'
WORDS = 'Use Markdown rather than a database for inspectability.'
DECISION = f'# Where to store pages\n\n“{WORDS}” [1]\n\n## Why\nInspectability. [1]\n\n## Sources\n- [1] {SOURCE}\n'


@pytest.fixture
def book(tmp_path):
    prepare(tmp_path)
    return Notebook(tmp_path)


def material(book):
    book.write('sessions/fixture.md', f'# Fixture\n\n## Decisions\n- “{WORDS}” [1]\n\n## Work\nPRIVATE WORK\n\n## Sources\n- [1] {SOURCE}\n')
    book.write('projects/fixture.md', f'# Fixture\n\n## Key decisions\n- 2026-11-01: “Keep pages inspectable.” [1]\n\n## Sources\n- [1] codex:fixture:8\n')


def cursor():
    return dict(phase='daily-update', batch={'done': True}, jobs=[], job_index=0,
                current=None, summaries=[], same_left=0, same_new_left=0, changed=[], slot=None)


def quiet(monkeypatch):
    from connectonion.rem import night, tasks
    monkeypatch.setattr(night, 'prepare', lambda *a, **kw: [])
    monkeypatch.setattr(tasks, 'auto_dispatch', lambda *a: None)
    monkeypatch.setattr(native_round, 'prepare_translation', lambda *a: None)
    monkeypatch.setattr(native_round, 'finish', lambda *a: None)


@pytest.fixture
def abstract_config(monkeypatch):
    from connectonion.rem import native
    quiet(monkeypatch)
    monkeypatch.setattr(native.quota, 'read', lambda *a: {})
    monkeypatch.setattr(native.runner, 'scrub_task', lambda *a: None)
    return default_config()


def decision_backlog(book, count):
    lines = [f'- “Choice {index}.” [1]' for index in range(count)]
    book.write('sessions/backlog.md', '# Backlog\n\n## Decisions\n' + '\n'.join(lines)
               + f'\n\n## Sources\n- [1] {SOURCE}\n')


def end_abstract(book, state, prepared, *, changed, outcome='completed'):
    from connectonion.rem import native
    name = Path(prepared['task']['directory']).name
    prepared.update(run={'id': name}, render_stage='abstract', id=name,
                    directory=prepared['task']['directory'])
    if outcome == 'completed':
        # These queue tests simulate promotion; a success must contain the
        # captured lines, rather than merely naming a nonexistent output page.
        for record in changed:
            if not book.exists(record):
                book.write(record, '# Captured choices\n\n' + prepared['task']['items'][0]['text'])
        native._accept(book.root, state, prepared, {'changed': changed})
    else:
        native._discard(book.root, state, prepared, 'No passing pages', outcome=outcome)


def test_two_successful_abstract_slices_in_one_night(book, abstract_config):
    decision_backlog(book, 40)
    state = cursor()
    for index in range(2):
        prepared = native_round.prepare_task(book.root, state, abstract_config, book.root / f'slice-{index}')
        assert prepared is not None, 'next successful slice must run in the same night'
        packet = '\n'.join(item['text'] for item in prepared['task']['items'])
        assert f'“Choice {index * 20}.”' in packet
        assert f'“Choice {index * 20 + 19}.”' in packet
        record = f'decisions/slice-{index}.md'
        Notebook(Path(prepared['task']['task_root'])).write(record, DECISION.replace(WORDS, f'Choice {index * 20}.'))
        prepared['directory'] = prepared['task']['directory']
        result = native_round.check_task(book.root, prepared, {'result': 'Captured choice'})
        assert result['changed'] == [record]
        end_abstract(book, state, prepared, changed=result['changed'])
    assert native_round.prepare_task(book.root, state, abstract_config, book.root / 'empty') is None


def test_native_verdict_only_rounds_drain_without_empty_stop(book, abstract_config, monkeypatch):
    from connectonion.rem import decisions, native
    decision_backlog(book, 45)
    write_json(state_path(book.root, 'round.json'), {**cursor(), 'started_at': service.now().isoformat()})
    monkeypatch.setattr(native, '_stop', lambda *a, **kw: (None, {'used_percent': 0}))
    for _ in range(3):
        offered = native.next_task(book.root)
        assert offered['outcome'] == 'task'
        task = native.pending(book.root)[0]
        folder = Path(task['directory'])
        items = json.loads((folder / 'material.json').read_text())
        ids = re.findall(r'(?m)^\[(d[0-9a-f]{12})\]', '\n'.join(item['text'] for item in items))
        (folder / 'report.md').write_text('\n'.join(f'VERDICT {identity} not-a-decision' for identity in ids))
        assert native.submit(book.root, offered['id'])['outcome'] == 'accepted'
    status = decisions.status(book.root)
    assert status['waiting'] == status['to_retry'] == 0
    assert status['skipped']['not_decision'] == 45


def test_native_refusal_does_not_block_independent_not_decision_verdicts(book, abstract_config, monkeypatch):
    from connectonion.rem import decisions, native
    decision_backlog(book, 3)
    write_json(state_path(book.root, 'round.json'), {**cursor(), 'started_at': service.now().isoformat()})
    monkeypatch.setattr(native, '_stop', lambda *a, **kw: (None, {'used_percent': 0}))
    offered = native.next_task(book.root)
    task = native.pending(book.root)[0]
    folder = Path(task['directory'])
    items = json.loads((folder / 'material.json').read_text())
    ids = re.findall(r'(?m)^\[(d[0-9a-f]{12})\]', '\n'.join(item['text'] for item in items))
    Notebook(Path(task['task']['task_root'])).write('decisions/bad.md',
        DECISION.replace(WORDS, 'Choice 0.') + '\nOriginating pages:\n[1]: ../sessions/backlog.md\n')
    (folder / 'report.md').write_text('\n'.join(f'VERDICT {identity} not-a-decision' for identity in ids[1:]))
    assert native.submit(book.root, offered['id'])['outcome'] == 'accepted'
    status = decisions.status(book.root)
    assert status['waiting'] == status['to_retry'] == status['lines']['refused'] == 1
    assert status['skipped']['not_decision'] == 2


@pytest.mark.parametrize('outcome', ['completed', 'discarded', 'parked'])
def test_abstract_moves_past_one_empty_and_stops_after_two(book, abstract_config, monkeypatch, rem_clock, outcome):
    from datetime import timedelta
    decision_backlog(book, 60)
    state = cursor()
    first = native_round.prepare_task(book.root, state, abstract_config, book.root / 'first')
    end_abstract(book, state, first, changed=['decisions/first.md'])
    failed = native_round.prepare_task(book.root, state, abstract_config, book.root / 'failed')
    assert failed is not None, 'a successful first slice must allow the failing second slice'
    end_abstract(book, state, failed, changed=[], outcome=outcome)
    following = native_round.prepare_task(book.root, cursor(), abstract_config, book.root / 'following')
    assert following is not None
    assert '“Choice 40.”' in following['task']['items'][0]['text']
    end_abstract(book, cursor(), following, changed=[], outcome=outcome)
    assert native_round.prepare_task(book.root, cursor(), abstract_config, book.root / 'stopped') is None
    monkeypatch.setattr(service, 'now', lambda: rem_clock + timedelta(days=1))
    retry = native_round.prepare_task(book.root, cursor(), abstract_config, book.root / 'retry')
    assert retry['task']['items'] == failed['task']['items']


def test_night_empty_then_success_preserves_failure_and_resets_streak(book, abstract_config):
    decision_backlog(book, 100)
    for index, changed in enumerate([[], ['decisions/second.md'], [], ['decisions/fourth.md'], []]):
        task = native_round.prepare_task(book.root, cursor(), abstract_config, book.root / f'slice-{index}')
        assert task is not None
        assert f'“Choice {index * 20}.”' in task['task']['items'][0]['text']
        end_abstract(book, cursor(), task, changed=changed)
    from connectonion.rem.captured_decisions import material as captured, pending_count
    assert pending_count(book) == 60
    assert '“Choice 0.”' in captured(book)[0]['text']
    marker = read_json(state_path(book.root, 'abstract-night.json'), {})
    assert marker['empty_rounds'] == 1 and marker['set_aside'] == 3


def test_replayed_empty_result_does_not_stop_next_reservation(book, abstract_config):
    from connectonion.rem import native
    decision_backlog(book, 60)
    first = native_round.prepare_task(book.root, cursor(), abstract_config, book.root / 'first')
    end_abstract(book, cursor(), first, changed=[])
    native._log(book.root, first, 'completed', changed=[])
    second = native_round.prepare_task(book.root, cursor(), abstract_config, book.root / 'second')
    assert second is not None and '“Choice 20.”' in second['task']['items'][0]['text']
    native._log(book.root, first, 'completed', changed=[])
    assert native_round.prepare_task(book.root, cursor(), abstract_config, book.root / 'pending') is None
    end_abstract(book, cursor(), second, changed=[])
    assert native_round.prepare_task(book.root, cursor(), abstract_config, book.root / 'stopped') is None
    marker = read_json(state_path(book.root, 'abstract-night.json'), {})
    assert marker['empty_rounds'] == 2 and marker['set_aside'] == 2


@pytest.mark.parametrize('cap', [None, 2])
def test_abstract_stops_at_nightly_round_cap(book, abstract_config, cap):
    decision_backlog(book, 140)
    if cap is not None:
        abstract_config['limits']['abstract_rounds_per_night'] = cap
    cap = cap or 6
    state = cursor()
    for index in range(cap):
        prepared = native_round.prepare_task(book.root, state, abstract_config, book.root / f'capped-{index}')
        assert prepared is not None, f'round {index + 1} must run before the cap'
        end_abstract(book, state, prepared, changed=[f'decisions/capped-{index}.md'])
    assert native_round.prepare_task(book.root, state, abstract_config, book.root / 'over-cap') is None
    assert read_json(state_path(book.root, 'abstract-night.json'), {})['rounds'] == cap


def test_abstract_restart_keeps_reserved_round_count(book, abstract_config):
    decision_backlog(book, 60)
    abstract_config['limits']['abstract_rounds_per_night'] = 2
    first = native_round.prepare_task(book.root, cursor(), abstract_config, book.root / 'first')
    end_abstract(book, cursor(), first, changed=['decisions/first.md'])
    second = native_round.prepare_task(book.root, cursor(), abstract_config, book.root / 'second')
    assert second is not None, 'a restart must resume the night after a successful slice'
    assert read_json(state_path(book.root, 'abstract-night.json'), {})['rounds'] == 2
    # A reserved turn cannot start a duplicate, or free its place at the cap.
    assert native_round.prepare_task(book.root, cursor(), abstract_config, book.root / 'pending') is None
    end_abstract(book, cursor(), second, changed=['decisions/second.md'])
    assert native_round.prepare_task(book.root, cursor(), abstract_config, book.root / 'restart-at-cap') is None


def test_abstract_next_night_resets_round_count(book, abstract_config, monkeypatch, rem_clock):
    from datetime import timedelta
    decision_backlog(book, 40)
    abstract_config['limits']['abstract_rounds_per_night'] = 1
    first = native_round.prepare_task(book.root, cursor(), abstract_config, book.root / 'first')
    end_abstract(book, cursor(), first, changed=['decisions/first.md'])
    assert native_round.prepare_task(book.root, cursor(), abstract_config, book.root / 'capped') is None
    monkeypatch.setattr(service, 'now', lambda: rem_clock + timedelta(days=1))
    second = native_round.prepare_task(book.root, cursor(), abstract_config, book.root / 'tomorrow')
    assert second is not None
    marker = read_json(state_path(book.root, 'abstract-night.json'), {})
    assert marker['day'] == '2026-09-08'
    assert marker.get('rounds') == 1, 'a new night starts at zero before reserving its first round'
    assert '“Choice 20.”' in second['task']['items'][0]['text']


@pytest.mark.parametrize('tail', ['same-person', 'translate'])
def test_abstract_cap_releases_later_night_jobs(book, abstract_config, monkeypatch, tail):
    from connectonion.rem import same_person
    decision_backlog(book, 140)
    state = cursor()
    for index in range(6):
        prepared = native_round.prepare_task(book.root, state, abstract_config, book.root / f'slice-{index}')
        end_abstract(book, state, prepared, changed=[f'decisions/slice-{index}.md'])
    if tail == 'same-person':
        state['same_left'] = 1
        monkeypatch.setattr(same_person, 'candidates', lambda root, *, uninvestigated:
                            [] if uninvestigated else [{'id': 'pair'}])
        monkeypatch.setattr(same_person, 'prepare', lambda *a, **kw: {})
    else:
        monkeypatch.setattr(native_round, 'prepare_translation', lambda *a: {'stage': 'translate'})
    following = native_round.prepare_task(book.root, state, abstract_config, book.root / 'following')
    assert following['stage'] == tail


def test_replayed_success_does_not_open_another_reserved_slice(book, abstract_config):
    from connectonion.rem import native
    decision_backlog(book, 60)
    first = native_round.prepare_task(book.root, cursor(), abstract_config, book.root / 'first')
    end_abstract(book, cursor(), first, changed=['decisions/first.md'])
    second = native_round.prepare_task(book.root, cursor(), abstract_config, book.root / 'second')
    native._log(book.root, first, 'completed', changed=['decisions/first.md'])
    assert native_round.prepare_task(book.root, cursor(), abstract_config, book.root / 'duplicate') is None
    end_abstract(book, cursor(), second, changed=['decisions/second.md'])
    assert native_round.prepare_task(book.root, cursor(), abstract_config, book.root / 'third') is not None


def test_third_failed_night_releases_gap_without_repeating_later_success(book, abstract_config, monkeypatch, rem_clock):
    from datetime import timedelta
    decision_backlog(book, 40)
    for day in range(3):
        monkeypatch.setattr(service, 'now', lambda: rem_clock + timedelta(days=day))
        failed = native_round.prepare_task(book.root, cursor(), abstract_config, book.root / f'failed-{day}')
        assert '“Choice 0.”' in failed['task']['items'][0]['text']
        end_abstract(book, cursor(), failed, changed=[])
        if day == 0:
            following = native_round.prepare_task(book.root, cursor(), abstract_config, book.root / 'later-success')
            assert '“Choice 20.”' in following['task']['items'][0]['text']
            end_abstract(book, cursor(), following, changed=['decisions/later.md'])
        assert native_round.prepare_task(book.root, cursor(), abstract_config, book.root / f'stopped-{day}') is None
    monkeypatch.setattr(service, 'now', lambda: rem_clock + timedelta(days=3))
    following = native_round.prepare_task(book.root, cursor(), abstract_config, book.root / 'following')
    assert following is None


def test_night_abstract_follows_summaries_and_stops_without_promotion(book, monkeypatch):
    quiet(monkeypatch)
    material(book)
    state = cursor()
    state['summaries'] = [{'record': 'sessions/fixture.md', 'key': 'fixture'}]
    monkeypatch.setattr(native_round.sessions, 'prepare', lambda *a, **kw: {})
    task = native_round.prepare_task(book.root, state, default_config(), book.root / 'summary-task')
    assert task['stage'] == 'sessions-summary'
    state['summaries'] = []
    monkeypatch.setattr('connectonion.rem.reflections.context', lambda *a: [
        {'role': 'reflection', 'source': 'reflection:unrelated', 'text': 'An unrelated proposal.'}])
    task = native_round.prepare_task(book.root, state, default_config(), book.root / 'abstract-task')
    assert task is not None and task['stage'] == 'abstract'
    assert task['handler'] == 'runner' and task['operation'] == 'abstract'
    texts = '\n'.join(i['text'] for i in task['task']['items'])
    assert WORDS in texts and 'Keep pages inspectable.' in texts
    assert 'PRIVATE WORK' not in texts and 'An unrelated proposal.' not in texts
    native_round.advance(book.root, state, task, {'changed': []})
    assert native_round.prepare_task(book.root, state, default_config(), book.root / 'again') is None
    assert native_round.prepare_task(book.root, cursor(), default_config(), book.root / 'restart') is None
    write_json(state_path(book.root, 'abstract-night.json'), {'day': '2020-01-01'})
    assert native_round.prepare_task(book.root, cursor(), default_config(), book.root / 'next-night')['stage'] == 'abstract'


@pytest.mark.parametrize('record,body', [('sessions/empty.md', ''),
                                        ('sessions/empty.md', '## Decisions\n- Unknown\n'),
                                        ('projects/empty.md', '## Key decisions\n- None yet.\n')])
def test_night_without_captured_decisions_has_no_model_turn(book, monkeypatch, record, body):
    quiet(monkeypatch)
    book.write(record, '# Empty\n\n' + body)
    monkeypatch.setattr(runner, 'prepare', lambda *a, **kw: pytest.fail('empty model turn'))
    assert native_round.prepare_task(book.root, cursor(), default_config(), book.root / 'task') is None


def task(book, tmp_path):
    material(book)
    directory = tmp_path / 'task'
    directory.mkdir()
    from connectonion.rem.captured_decisions import material as captured
    return runner.prepare(book, captured(book), default_config(), stage='abstract', directory=directory, native=True)


@pytest.mark.parametrize('record', ['people/other.md', 'projects/other.md', 'notes/other.md', 'unexpected.txt'])
def test_abstract_refuses_other_paths_before_any_promotion(book, tmp_path, record):
    prepared = task(book, tmp_path)
    output = Path(prepared['task_root'])
    (output / record).parent.mkdir(parents=True, exist_ok=True)
    (output / record).write_text('# Not permitted\n')
    Notebook(output).write('decisions/valid.md', DECISION)
    with pytest.raises(runner.RunFailed, match='only decisions/, knowledge/ and principles/'):
        runner.check(prepared, {}, native=True)
    assert not book.exists('decisions/valid.md')


def test_abstract_promotes_twenty_sourced_pages_and_updates_existing_question(book, tmp_path):
    book.write('decisions/existing.md', DECISION)
    prepared = task(book, tmp_path)
    output = Notebook(Path(prepared['task_root']))
    output.write('decisions/existing.md', DECISION.replace('Inspectability.', 'Inspectability and portability.'))
    for index in range(18):
        output.write(f'decisions/choice-{index}.md', DECISION)
    output.write('principles/inspection.md', '# Prefer inspection\n\nDrawn from:\n'
                 '- [First](../decisions/choice-0.md)\n- [Second](../decisions/choice-1.md)\n'
                 '- [Third](../decisions/choice-2.md)\n')
    runner.check(prepared, {}, native=True)
    assert len(book.list('decisions')) == 19
    assert book.list('principles') == ['principles/inspection.md']
    assert 'portability' in book.read('decisions/existing.md')


def test_abstract_refuses_twenty_one_pages(book, tmp_path):
    prepared = task(book, tmp_path)
    for index in range(21):
        Notebook(Path(prepared['task_root'])).write(f'decisions/choice-{index}.md', DECISION)
    with pytest.raises(runner.RunFailed, match='at most 20'):
        runner.check(prepared, {}, native=True)
    assert book.list('decisions') == []


@pytest.mark.parametrize('text', [DECISION.replace(f'“{WORDS}”', 'The assistant proposed a database.'),
                                       DECISION.replace('## Sources\n- [1] ' + SOURCE, '## Sources\n- [1] unknown-source')])
def test_abstract_refuses_unquoted_or_unsourced_decision(book, tmp_path, text):
    prepared = task(book, tmp_path)
    Notebook(Path(prepared['task_root'])).write('decisions/proposal.md', text)
    with pytest.raises(runner.RunFailed):
        runner.check(prepared, {}, native=True)
    assert not book.exists('decisions/proposal.md')


def test_decision_page_review_reuses_owner_quote_check():
    from connectonion.rem.page_review import unquoted_decisions
    errors = unquoted_decisions(DECISION.replace(f'“{WORDS}”', 'The assistant proposed a database.'), decision_page=True)
    assert any("owner's words" in error for error in errors)


def test_night_prompt_preserves_skill_and_describes_material_and_bound(book, tmp_path):
    prepared = task(book, tmp_path)
    prompt = prepared['prompt']
    assert 'at most 20' in prompt and 'only decisions/, knowledge/ and principles/' in prompt
    assert '## Decisions' in prompt and '## Key decisions' in prompt
    assert "assistant's proposal" in prompt
    assert 'Write at most one NEW page' not in prompt
    assert 'Three decisions minimum' in (tmp_path / 'task/instructions.md').read_text()


def test_cli_docs_describe_night_abstract():
    root = Path(__file__).resolve().parents[2]
    for path in ['docs/cli/rem.md', 'connectonion/cli/commands/rem_help.md']:
        text = (root / path).read_text()
        assert 'After session summaries, the night' in text
        assert '20' in text and 'decisions/' in text and 'principles/' in text
        assert 'ceil(N / 20 / rounds)' in text
        assert 'limits.abstract_rounds_per_night' in text


def test_native_abstract_hashes_canonical_inputs_but_not_editable_output(book, tmp_path):
    from connectonion.rem import native
    book.write('decisions/existing.md', DECISION)
    prepared = task(book, tmp_path)
    hashes = native._inputs(book.root, prepared, Path(prepared['directory']), handler='runner')
    output = Path(prepared['task_root']) / 'decisions/existing.md'
    assert str(output) not in hashes
    assert str(book.path('decisions/existing.md')) in hashes
    assert str(book.path('sessions/fixture.md')) in hashes


def test_unfinished_abstract_is_not_reserved_twice_across_midnight(book, monkeypatch):
    from datetime import datetime, timezone
    quiet(monkeypatch)
    material(book)
    monkeypatch.setattr(service, 'now', lambda: datetime(2026, 11, 1, 23, tzinfo=timezone.utc))
    assert native_round.prepare_task(book.root, cursor(), default_config(), book.root / 'evening')
    monkeypatch.setattr(service, 'now', lambda: datetime(2026, 11, 2, 6, tzinfo=timezone.utc))
    assert native_round.prepare_task(book.root, cursor(), default_config(), book.root / 'morning') is None
    monkeypatch.setattr(service, 'now', lambda: datetime(2026, 11, 2, 23, tzinfo=timezone.utc))
    assert native_round.prepare_task(book.root, cursor(), default_config(), book.root / 'tomorrow')


def test_abstract_refuses_invented_owner_quote(book, tmp_path):
    prepared = task(book, tmp_path)
    Notebook(Path(prepared['task_root'])).write('decisions/proposal.md', DECISION.replace(WORDS, 'Use the database as the assistant suggested.'))
    with pytest.raises(runner.RunFailed, match="owner's words"):
        runner.check(prepared, {}, native=True)
    assert not book.exists('decisions/proposal.md')


def test_abstract_receipt_covers_whole_batch(book, tmp_path):
    from connectonion.rem import native
    prepared = task(book, tmp_path)
    output = Notebook(Path(prepared['task_root']))
    output.write('decisions/one.md', DECISION)
    output.write('decisions/two.md', DECISION)
    runner.check(prepared, {}, native=True)
    saved = {'directory': prepared['directory'], 'task': prepared}
    assert native._promoted(book.root, saved)
    assert native._recovered_result(book.root, saved)['changed'] == ['decisions/one.md', 'decisions/two.md']
    book.write('decisions/one.md', DECISION + '\nAn external edit.\n')
    assert not native._promoted(book.root, saved)


def test_abstract_refuses_linked_output(book, tmp_path):
    prepared = task(book, tmp_path)
    output = Path(prepared['task_root'])
    (output / 'decisions').mkdir(exist_ok=True)
    (output / 'decisions/linked.md').symlink_to(book.path('sessions/fixture.md'))
    with pytest.raises(runner.RunFailed, match='only decisions/, knowledge/ and principles/'):
        runner.check(prepared, {}, native=True)


def test_mixed_abstract_promotes_good_pages_and_records_refusal(book, tmp_path, monkeypatch):
    from connectonion.rem import native
    prepared = task(book, tmp_path)
    output = Notebook(Path(prepared['task_root']))
    for name in ('one', 'two'):
        output.write(f'decisions/{name}.md', DECISION)
    output.write('decisions/bad.md', DECISION.replace(f'“{WORDS}”', 'An assistant proposal.'))
    saved = dict(directory=prepared['directory'], task=prepared, handler='runner', record='', operation='abstract')
    result = native_round.check_task(book.root, saved, {'result': 'Three candidates'})
    assert result['changed'] == ['decisions/one.md', 'decisions/two.md']
    assert result['refused'][0]['record'] == 'decisions/bad.md'
    assert result['refused'][0]['errors']
    assert not book.exists('decisions/bad.md')
    saved.update(run={'id': 'mixed'}, render_stage='abstract', id='native-test')
    monkeypatch.setattr(native.quota, 'read', lambda *a: {})
    monkeypatch.setattr(native.runner, 'scrub_task', lambda *a: None)
    native._accept(book.root, cursor(), saved, result)
    assert read_json(state_path(book.root, 'runs/mixed.json'), {})['refused'] == result['refused']


def test_captured_packet_budget_and_only_bound_sources(book):
    from connectonion.rem.captured_decisions import material as captured
    material(book)
    page = book.read('sessions/fixture.md') + '- [9] codex:unused ' + 'unrelated ' * 1000 + '\n'
    book.write('sessions/fixture.md', page)
    config = default_config()
    config['limits']['input_chars_per_batch'] = 600
    items = captured(book, config)
    import json
    assert items and len(json.dumps(items, ensure_ascii=False, indent=2)) + 1 <= 600
    assert all('codex:unused' not in i['text'] for i in items)


def test_offered_sections_are_oldest_first_changed_and_crash_retry(book, monkeypatch):
    from connectonion.rem import native
    import os
    material(book)
    os.utime(book.path('projects/fixture.md'), (1, 1))
    os.utime(book.path('sessions/fixture.md'), (2, 2))
    config = default_config()
    config['limits']['input_chars_per_batch'] = 600
    first = native_round.prepare_abstract(book.root, cursor(), config, book.root / 'first')
    assert [i['record'] for i in first['task']['items']] == ['projects/fixture.md']
    # Reservation alone is not an offered receipt: a crash must retry next night.
    state = state_path(book.root, 'abstract-night.json')
    write_json(state, {'day': '2020-01-01'})
    retry = native_round.prepare_abstract(book.root, cursor(), config, book.root / 'retry')
    assert retry['task']['items'] == first['task']['items']
    retry.update(run={'id': 'offered'}, render_stage='abstract', id='native-test', directory=retry['task']['directory'])
    monkeypatch.setattr(native.quota, 'read', lambda *a: {})
    monkeypatch.setattr(native.runner, 'scrub_task', lambda *a: None)
    book.write('decisions/first.md', '# Captured choice\n\n' + retry['task']['items'][0]['text'])
    native._accept(book.root, cursor(), retry, {'changed': ['decisions/first.md']})
    write_json(state, {'day': '2020-01-01'})
    second = native_round.prepare_abstract(book.root, cursor(), config, book.root / 'second')
    assert [i['record'] for i in second['task']['items']] == ['sessions/fixture.md']
    second.update(run={'id': 'second'}, render_stage='abstract', id='native-test', directory=second['task']['directory'])
    book.write('decisions/second.md', '# Captured choice\n\n' + second['task']['items'][0]['text'])
    native._accept(book.root, cursor(), second, {'changed': ['decisions/second.md']})
    write_json(state, {'day': '2020-01-01'})
    assert native_round.prepare_abstract(book.root, cursor(), config, book.root / 'empty') is None
    book.write('projects/fixture.md', book.read('projects/fixture.md').replace('inspectable', 'portable'))
    changed = native_round.prepare_abstract(book.root, cursor(), config, book.root / 'changed')
    assert [i['record'] for i in changed['task']['items']] == ['projects/fixture.md']


def test_existing_unquoted_decision_can_be_maintained():
    original = DECISION.replace(f'“{WORDS}”', 'Use Markdown for inspectability.')
    candidate = original.replace('## Why\nInspectability.', '## Why\nInspectability and portability.')
    assert validate('decisions/legacy.md', candidate, original, [{'source': SOURCE, 'text': WORDS}]) == []


def test_maintain_prompt_is_byte_identical_to_main(book, tmp_path):
    import subprocess
    import types
    source = subprocess.run(['git', 'show', 'HEAD:connectonion/rem/runner.py'],
                            capture_output=True, text=True, check=True).stdout
    baseline = types.ModuleType('connectonion.rem._baseline_runner')
    baseline.__file__ = runner.__file__
    baseline.__package__ = 'connectonion.rem'
    exec(compile(source, runner.__file__, 'exec'), baseline.__dict__)
    directory = tmp_path / 'maintain'
    directory.mkdir()
    items = [{'source': SOURCE, 'text': WORDS}]
    expected = baseline.prepare(book, items, default_config(), directory=directory, native=True)['prompt']
    actual = runner.prepare(book, items, default_config(), directory=directory, native=True)['prompt']
    assert actual == expected


def test_large_section_progresses_in_bounded_packets(book):
    import json
    from connectonion.rem.captured_decisions import material as captured, remember_offered
    lines = [f'- “Choose inspectable storage variant {i}.” [1]' for i in range(25)]
    book.write('sessions/large.md', '# Large\n\n## Decisions\n' + '\n'.join(lines) + f'\n\n## Sources\n- [1] {SOURCE}\n')
    config = default_config()
    config['limits']['input_chars_per_batch'] = 650
    packets = []
    for _ in range(25):
        items = captured(book, config)
        if not items:
            break
        assert len(json.dumps(items, ensure_ascii=False, indent=2)) + 1 <= 650
        packets.extend(i['text'] for i in items)
        remember_offered(book.root, items)
    assert captured(book, config) == []
    assert all(any(line in packet for packet in packets) for line in lines)


def test_outcome_must_be_durable_before_sections_are_marked_offered(book, monkeypatch):
    from connectonion.rem import native
    from connectonion.rem.captured_decisions import material as captured
    material(book)
    items = captured(book)
    saved = {'run': {'id': 'crash'}, 'operation': 'abstract', 'task': {'items': items}, 'directory': str(book.root)}
    def fail_record(*a, **kw):
        raise OSError('simulated outcome write failure')
    monkeypatch.setattr(native, 'write_json', fail_record)
    with pytest.raises(OSError, match='outcome write failure'):
        native._log(book.root, saved, 'discarded')
    assert captured(book) == items


def test_runner_uses_supplied_abstract_items_once(book, tmp_path, monkeypatch):
    from connectonion.rem import captured_decisions
    material(book)
    items = captured_decisions.material(book)[:1]
    monkeypatch.setattr(captured_decisions, 'material', lambda *a: pytest.fail('material recomputed'))
    directory = tmp_path / 'supplied'
    directory.mkdir()
    prepared = runner.prepare(book, items, default_config(), stage='abstract', directory=directory, native=True)
    assert prepared['items'] == items


def test_repairable_refusal_and_parking_keep_material_pending(book):
    from connectonion.rem import native
    from connectonion.rem.captured_decisions import material as captured
    material(book)
    items = captured(book)
    saved = {'run': {'id': 'refused'}, 'operation': 'abstract', 'task': {'items': items}, 'directory': str(book.root)}
    native._log(book.root, saved, 'refused', reason='Missing quotes')
    assert captured(book) == items
    native._log(book.root, saved, 'parked', reason='Repeated refusal')
    assert captured(book) == items


@pytest.mark.parametrize('sections', [60, 1])
def test_nightly_packet_matches_page_capacity_and_drains(book, sections):
    import os
    from connectonion.rem.captured_decisions import material as captured, remember_offered, NIGHT_PAGE_LIMIT
    for index in range(sections):
        lines = [f'- 2026-11-01: “Choice {i}.” [1]' for i in
                 (range(60) if sections == 1 else [index])]
        record = f'sessions/choices-{index:02}.md'
        book.write(record, '# Choices\n\n## Decisions\n' + '\n'.join(lines) + f'\n\n## Sources\n- [1] {SOURCE}\n')
        os.utime(book.path(record), (index + 1, index + 1))
    for night in range(3):
        items = captured(book)
        lines = [line for item in items for line in item['text'].splitlines()
                 if line.startswith('[d') and '] - 2026' in line]
        assert len(lines) == NIGHT_PAGE_LIMIT
        assert f'“Choice {night * 20}.”' in lines[0]
        assert f'“Choice {night * 20 + 19}.”' in lines[-1]
        remember_offered(book.root, items)
    assert captured(book) == []


@pytest.mark.parametrize('outcome', ['completed', 'discarded', 'parked'])
def test_failed_slice_retries_then_gives_up_on_three_distinct_nights(book, monkeypatch, outcome):
    from datetime import datetime, timezone
    from connectonion.rem import native
    from connectonion.rem.captured_decisions import material as captured
    material(book)
    items = captured(book)
    saved = {'run': {'id': 'failure'}, 'operation': 'abstract', 'task': {'items': items}, 'directory': str(book.root)}
    monkeypatch.setattr(native.quota, 'read', lambda *a: {})
    for day in range(1, 4):
        monkeypatch.setattr(service, 'now', lambda: datetime(2026, 11, day, 23, tzinfo=timezone.utc))
        native._log(book.root, saved, outcome, changed=[], reason='No passing pages')
        native._log(book.root, saved, outcome, changed=[], reason='Repeated log same night')
        if day < 3:
            assert captured(book) == items
    assert captured(book) == []
    state = read_json(state_path(book.root, 'abstract-offered.json'), {})
    for item in items:
        given_up = state[item['record']]['given_up'][0]
        assert given_up['end'] == item['section_end']
        assert len(given_up['nights']) == 3
        assert given_up['reason'] == 'No passing pages'
    book.write('sessions/fixture.md', book.read('sessions/fixture.md').replace('Markdown', 'plain text'))
    assert [item['record'] for item in captured(book)] == ['sessions/fixture.md']


def test_given_up_slice_releases_next_oldest_packet(book, monkeypatch):
    from datetime import datetime, timezone
    from connectonion.rem import native
    from connectonion.rem.captured_decisions import material as captured
    import os
    for index in range(21):
        record = f'sessions/choice-{index:02}.md'
        book.write(record, f'# Choice\n\n## Decisions\n- “Choose {index}.” [1]\n\n## Sources\n- [1] {SOURCE}\n')
        os.utime(book.path(record), (index + 1, index + 1))
    items = captured(book)
    saved = {'run': {'id': 'blocked-slice'}, 'operation': 'abstract', 'task': {'items': items}, 'directory': str(book.root)}
    monkeypatch.setattr(native.quota, 'read', lambda *a: {})
    for day in range(1, 4):
        monkeypatch.setattr(service, 'now', lambda: datetime(2026, 11, day, 23, tzinfo=timezone.utc))
        native._log(book.root, saved, 'completed', changed=[])
    assert [item['record'] for item in captured(book)] == ['sessions/choice-20.md']


def test_resumed_task_counts_its_reserved_night_only(book, monkeypatch):
    from datetime import datetime, timezone
    from connectonion.rem import native
    from connectonion.rem.captured_decisions import material as captured
    material(book)
    items = captured(book)
    saved = {'run': {'id': 'resumed'}, 'operation': 'abstract',
             'task': {'items': items, 'abstract_night': '2026-11-01'}, 'directory': str(book.root)}
    for day in range(1, 4):
        monkeypatch.setattr(service, 'now', lambda: datetime(2026, 11, day, 23, tzinfo=timezone.utc))
        native._log(book.root, saved, 'parked', reason='No passing pages')
    assert captured(book) == items
    state = read_json(state_path(book.root, 'abstract-offered.json'), {})
    assert all(list(row['failures'].values()) == [['2026-11-01']] for row in state.values())
