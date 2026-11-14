"""Faults a 2026-11-03 real-account run found in Asana -> REM, each kept fixed here.

1. An investigation's Asana citations resolve to the saved version cited;
2. A project's rolling agenda page is maintained with the project page;
3. A one-page turn may not drop a cited task the batch did not include;
4. A no-change sync points at a command that works.
Synthetic material through the exporter and FakeAsana; no token, no network.
"""

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from connectonion.rem.config import prepare
from connectonion.rem.files import Notebook, state_path, write_json
from connectonion.rem.reader_model import cited_context
from connectonion.useful_tools import asana_export as export
from tests.unit.test_asana_export import ACCOUNT, PROJECT, TASK, _task
from tests.unit.test_rem_asana import _batch, _save, asana_material  # noqa: F401 - pytest fixture

pytestmark = pytest.mark.unit


@pytest.fixture
def notebook(asana_material, tmp_path):
    """An Asana-only notebook whose saved subscription is the fixture's source."""
    source, client = asana_material
    root = tmp_path / 'rem'
    prepare(root)
    write_json(state_path(root, 'subscriptions.json'), {'asana': source})
    return root, source, client


def _page(sources: list[str]) -> str:
    lines = '\n'.join(f'- [{n}] {s} — 2026-11-03' for n, s in enumerate(sources, 1))
    return f'# Atlas\n\n## Facts\n\n- Due [1]\n\n## Sources\n\n{lines}\n'


def _contexts(root, sources):
    return cited_context(root, [{'text': _page(sources)}])


# -- citations resolve to the cited version -------------------------------------------------------------------------------

def test_a01_cited_snapshot_resolves_to_its_own_version(notebook):
    """A page cites the version it was written from; a newer sync must not change what it shows."""
    root, source, client = notebook
    client.tasks[TASK].update(name='ATLAS-04', due_on='2026-11-10', notes='Baseline v1')
    _save(source, client)
    [old] = _batch(source).items
    client.tasks[TASK].update(due_on='2026-11-12', notes='Baseline v2')
    _save(source, client)
    [new] = _batch(source).items
    assert old['source'] != new['source']
    found = _contexts(root, [old['source'], new['source']])
    assert 'Due: 2026-11-10' in found[old['source']]['excerpt'] and 'v1' in found[old['source']]['excerpt']
    assert 'Due: 2026-11-12' in found[new['source']]['excerpt'] and 'v2' in found[new['source']]['excerpt']
    assert found[new['source']]['source'] == 'asana'


def test_a01_claim_audit_packet_has_every_valid_asana_citation(notebook):
    from connectonion.rem.project_claim_review import packet
    root, source, client = notebook
    _save(source, client)
    [item] = _batch(source).items
    material, missing = packet(Notebook(root), _page([item['source']]))
    assert missing == [] and material['sources'][0]['context']['excerpt'].startswith('Asana task:')


@pytest.mark.parametrize('break_it', ['offset', 'account', 'task', 'uncommitted', 'not_a_line'])
def test_a01_an_invalid_citation_stays_unresolved(notebook, break_it):
    root, source, client = notebook
    _save(source, client)
    [item] = _batch(source).items
    prefix, account, task, daily, offset = item['source'].split(':')
    wrong = {'offset': f'{prefix}:{account}:{task}:{daily}:{int(offset) + 1}',
             'account': f'{prefix}:999:{task}:{daily}:{offset}',
             'task': f'{prefix}:{account}:999:{daily}:{offset}',
             'uncommitted': f'{prefix}:{account}:{task}:{daily}:{10 ** 9}',
             'not_a_line': f'{prefix}:{account}:{task}:../state.json:{offset}'}[break_it]
    assert _contexts(root, [wrong]) == {}


@pytest.mark.parametrize('change', ['other_project', 'disabled', 'not_consented', 'no_subscription'])
def test_a01_a_citation_outside_the_subscription_stays_unresolved(notebook, change):
    root, source, client = notebook
    _save(source, client)
    [item] = _batch(source).items
    saved = dict(source)
    if change == 'other_project':
        saved['project_gids'] = ['999']
    elif change == 'disabled':
        saved['enabled'] = False
    elif change == 'not_consented':
        saved['consented'] = False
    write_json(state_path(root, 'subscriptions.json'), {} if change == 'no_subscription' else {'asana': saved})
    assert _contexts(root, [item['source']]) == {}


def test_a01_resolving_reads_no_token_and_writes_nothing(notebook, monkeypatch):
    root, source, client = notebook
    _save(source, client)
    [item] = _batch(source).items
    monkeypatch.setattr('connectonion.useful_tools.asana._token',
                        lambda *a, **k: pytest.fail('a citation must not read the Asana token'))
    before = {p: p.read_bytes() for p in Path(source['root']).rglob('*') if p.is_file()}
    assert item['source'] in _contexts(root, [item['source']])
    assert before == {p: p.read_bytes() for p in Path(source['root']).rglob('*') if p.is_file()}


def test_a01_excerpt_budget_still_applies(notebook):
    root, source, client = notebook
    _save(source, client)
    [item] = _batch(source).items
    found = cited_context(root, [{'text': _page([item['source']])}], budget=20)
    assert len(found[item['source']]['excerpt']) == 20 and found[item['source']]['truncated']


# -- the agenda page moves with the project page -------------------------------------------------------------------------------

def _atlas_notebook(root):
    notebook = Notebook(root)
    notebook.write('projects/atlas-launch.md', '# Atlas Launch\n\n## Facts\n\n- Status: open\n')
    notebook.write('agenda/atlas-launch.md',
                   '# Atlas Launch agenda\n\nRelated: [Atlas Launch](../projects/atlas-launch.md)\n')
    notebook.write('agenda/beacon.md', '# Beacon agenda\n')
    return notebook


def test_a03_an_asana_batch_also_leads_to_the_projects_agenda_page(tmp_path):
    from connectonion.rem.leads import page_leads
    prepare(tmp_path)
    notebook = _atlas_notebook(tmp_path)
    item = {'source': f'asana:{ACCOUNT}:{TASK}:daily/2026/11/03.jsonl:0',
            'text': 'Asana task: ATLAS-04\nProjects: CO REM Test - Atlas Launch\nDue: 2026-11-12'}
    leads = page_leads(notebook, [item])
    assert leads[:2] == ['projects/atlas-launch.md', 'agenda/atlas-launch.md']
    assert 'agenda/beacon.md' not in leads


def test_a03_the_agenda_page_is_found_by_its_link_not_only_its_file_name(tmp_path):
    from connectonion.rem.leads import page_leads
    prepare(tmp_path)
    notebook = _atlas_notebook(tmp_path)
    notebook.write('agenda/launch-deadlines.md', notebook.read('agenda/atlas-launch.md'))
    item = {'source': f'asana:{ACCOUNT}:{TASK}:daily/2026/11/03.jsonl:0', 'text': 'Projects: Atlas Launch'}
    assert {'agenda/atlas-launch.md', 'agenda/launch-deadlines.md'} <= set(page_leads(notebook, [item]))


def test_a03_other_sources_do_not_spend_a_turn_on_agenda_pages(tmp_path):
    from connectonion.rem.leads import page_leads
    prepare(tmp_path)
    notebook = _atlas_notebook(tmp_path)
    leads = page_leads(notebook, [{'source': 'codex:s1:1', 'text': 'Worked on Atlas Launch today.'}])
    assert leads == ['projects/atlas-launch.md']


def test_a03_the_agenda_page_is_not_skipped_as_already_read(tmp_path):
    """The real run: the new date reached the project page and the agenda kept 10 November."""
    from connectonion.rem.leads import nothing_new
    prepare(tmp_path)
    _atlas_notebook(tmp_path)
    item = {'source': f'asana:{ACCOUNT}:{TASK}:daily/2026/11/03.jsonl:9246', 'role': 'other',
            'text': 'Asana task: ATLAS-04\nProjects: Atlas Launch\nDue: 2026-11-12'}
    assert not nothing_new(Notebook(tmp_path), 'agenda/atlas-launch.md', [item])


# -- a maintenance turn keeps tasks it was not given -------------------------------------------------------------------------------

def _cid(task, offset):
    return f'asana:{ACCOUNT}:{task}:daily/2026/11/03.jsonl:{offset}'


ORIGINAL = ('# Atlas Launch\n\n## Where it stands\n\n- ATLAS-04 is due 2026-11-12 (v2). [1]\n'
            '- ATLAS-05 tracks the browser check. [2]\n\n## Sources\n\n'
            f'- [1] {_cid("304", 9246)} — 2026-11-03\n- [2] {_cid("305", 7532)} — 2026-11-03\n')


def test_a04_dropping_a_task_the_batch_did_not_include_is_refused():
    from connectonion.rem.runner import CARRIED_ASANA, dropped_asana_tasks
    rewritten = ('# Atlas Launch\n\n## Where it stands\n\n- Eric rechecked staging. [1]\n\n## Sources\n\n'
                 f'- [1] {_cid("305", 11177)} — 2026-11-03\n')
    errors = dropped_asana_tasks('projects/atlas-launch.md', ORIGINAL, rewritten,
                                 [{'source': _cid('305', 11177)}])
    assert len(errors) == 1 and errors[0].startswith(CARRIED_ASANA) and 'task 304' in errors[0]


def test_a04_keeping_the_carried_task_and_rewriting_the_batch_task_is_accepted():
    from connectonion.rem.runner import dropped_asana_tasks
    kept = ORIGINAL.replace(_cid('305', 7532), _cid('305', 11177)).replace(
        'tracks the browser check', 'was rechecked by Eric')
    assert dropped_asana_tasks('projects/atlas-launch.md', ORIGINAL, kept, [{'source': _cid('305', 11177)}]) == []


def test_a04_a_task_seen_again_may_leave_the_page():
    from connectonion.rem.runner import dropped_asana_tasks
    only_five = ORIGINAL.replace('- ATLAS-04 is due 2026-11-12 (v2). [1]\n', '').replace(
        f'- [1] {_cid("304", 9246)} — 2026-11-03\n', '')
    assert dropped_asana_tasks('projects/atlas-launch.md', ORIGINAL, only_five,
                               [{'source': _cid('304', 12000)}, {'source': _cid('305', 11177)}]) == []


def test_a04_an_agenda_line_whose_date_has_passed_may_go():
    from connectonion.rem.runner import dropped_asana_tasks
    agenda = ('# Atlas agenda\n\n## Agenda\n\n- Due 2020-01-07: ATLAS-01. [1]\n- Due 2999-01-01: ATLAS-02. [2]\n\n'
              f'## Sources\n\n- [1] {_cid("301", 0)} — 2020-01-01\n- [2] {_cid("302", 10)} — 2026-11-03\n')
    without_both = '# Atlas agenda\n\n## Agenda\n\n- Due 2026-11-12: ATLAS-04. [1]\n\n## Sources\n\n' \
                   f'- [1] {_cid("304", 9246)} — 2026-11-03\n'
    errors = dropped_asana_tasks('agenda/atlas-launch.md', agenda, without_both, [{'source': _cid('304', 9246)}])
    assert len(errors) == 1 and 'task 302' in errors[0]


def test_a04_other_sources_are_not_checked():
    from connectonion.rem.runner import dropped_asana_tasks
    assert dropped_asana_tasks('projects/atlas-launch.md', ORIGINAL, '# Atlas Launch\n',
                               [{'source': 'codex:s1:1'}]) == []


def test_a04_a_refused_maintenance_turn_is_told_to_put_the_carried_tasks_back(tmp_path):
    """A batch holds only what changed: the repair names the dropped Asana tasks and says to restore them."""
    from connectonion.rem import runner
    errors = [f"{runner.CARRIED_ASANA}: task 304 (asana:1:304:daily/2026/11/02.jsonl:0) was not in this batch, "
              "so its lines and citation stay"]
    text = runner.repair_instruction('projects/atlas-launch.md', errors, tmp_path / 'task', tmp_path / 'work')
    assert 'were not in this batch' in text and 'exact Sources entry' in text
    assert str(tmp_path / 'work' / 'projects/atlas-launch.md') in text
    other = runner.repair_instruction('projects/atlas-launch.md', ['History has 9 lines'], tmp_path / 'task',
                                      tmp_path / 'work')
    assert 'were not in this batch' not in other


# -- a no-change sync points at status -------------------------------------------------------------------------------

@pytest.mark.parametrize('kept', [False, True])
def test_a02_no_change_sync_names_a_command_that_works(tmp_path, monkeypatch, kept):
    from connectonion.cli.main import app
    from connectonion.rem import service
    root = tmp_path / 'notebook'
    prepare(root)
    record = {'id': 'run_abc', 'outcome': 'no_change' if not kept else 'completed', 'items': 0 if not kept else 1,
              'runner_attempts': 0, 'changed': [], 'warning': ''}
    if kept:
        write_json(state_path(root, 'runs/run_abc.json'), record)
    monkeypatch.setattr(service, 'run_sync', lambda *a, **k: record)
    result = CliRunner().invoke(app, ['rem', '--root', str(root), '--json', 'sync', '--source', 'asana'])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert str(root) in payload['next']
    assert payload['next'].endswith(' logs run_abc' if kept else ' status')
    text = CliRunner().invoke(app, ['rem', '--root', str(root), 'sync', '--source', 'asana'])
    assert 'logs run_abc' not in text.output or kept


# -- the token owner's person page keeps its writes-to section -------------------------------------------------------------------------------

PERSON = ('# Eric z\n\n## How they communicate\n- Short comments. [1]\n\n## Cadence\n- Afternoons. [1]\n\n'
          '## Uncertainties\n- Unknown\n\n## Sources\n- [1] asana:100:300:daily/2026/11/03.jsonl:0 — 2026-11-03\n')


def _stub(writes_to: str) -> str:
    return f'# Eric z\n\n## How the user writes to them\n{writes_to}\n\n## Cadence\n- Unknown\n'


def test_a05_a_person_candidate_that_left_out_writes_to_gets_it_back_as_unknown():
    """Asana's "(you)" made a real turn treat a gid-matched page as the owner page, twice."""
    from connectonion.rem.page_review import restore_writes_to
    fixed = restore_writes_to('people/eric-z.md', PERSON, _stub('- Unknown — not investigated yet'))
    assert fixed.count('## How the user writes to them\n- Unknown\n') == 1
    assert fixed.index('## How the user writes to them') < fixed.index('## Cadence')


def test_a05_cited_writes_to_lines_are_not_replaced_by_unknown():
    from connectonion.rem.page_review import restore_writes_to
    original = _stub('- Opens with "Hi Eric". [2]')
    assert restore_writes_to('people/eric-z.md', PERSON, original) == PERSON


@pytest.mark.parametrize('record, owner', [('people/eric-z.md', True), ('projects/atlas.md', False)])
def test_a05_the_owner_page_and_other_pages_are_left_alone(record, owner):
    from connectonion.rem.page_review import restore_writes_to
    assert restore_writes_to(record, PERSON, _stub('- Unknown'), owner=owner) == PERSON


def test_a05_a_candidate_that_kept_the_section_is_unchanged():
    from connectonion.rem.page_review import restore_writes_to
    kept = PERSON.replace('## Cadence', '## How the user writes to them\n- Unknown\n\n## Cadence')
    assert restore_writes_to('people/eric-z.md', kept, _stub('- Unknown')) == kept
