"""The owner's coding-agent tasks are work, and their Insight has a higher floor."""

import json

import pytest

from connectonion.rem import investigate as inv, page_review, runner
from connectonion.rem.config import prepare
from connectonion.rem.files import Notebook, state_path, write_json


TASKS = [
    '- The user asked for the monthly-spend ledger. [1]',
    '- The user asked the assistant to research hotels. [1][2]',
]
OWED = '- Send the monthly ledger to Theo Park. [1][3]'


@pytest.fixture
def owner_page(tmp_path):
    root = tmp_path / 'rem'
    prepare(root)
    notebook = Notebook(root)
    record = 'people/avery.md'
    notebook.stub_person(record, 'Avery Lin', ['avery@example.com'], email='avery@example.com')
    write_json(state_path(root, 'map.json'), {'owner': {'record': record}})
    original = notebook.read(record)
    page = original.replace('- Unknown — not investigated yet', '- Unknown')
    page = page.replace('## Who they are\n- Unknown', '## Who they are\n- Builds reporting tools. [1]')
    page = page.replace('## Open threads\n- Unknown', '## Open threads\n' + '\n'.join([*TASKS, OWED]))
    page = page.replace('- (none yet)', '- [1] codex:avery:1\n- [2] claude-code:avery:2\n- [3] gmail:theo:1')
    items = [{'source': source} for source in ('codex:avery:1', 'claude-code:avery:2', 'gmail:theo:1')]
    return notebook, record, original, page, items


@pytest.mark.parametrize('newline', ['\n', '\r\n'])
def test_agent_threads_requires_every_citation_to_resolve_to_a_coding_session(owner_page, newline):
    _, _, _, page, _ = owner_page
    page = page.replace('## Open threads\n', '## Open threads\n'
                        '- Uncited task.\n- Unresolved task. [1][99]\n'
                        '- Read the hotel website. [1][W1]\n'
                        '- [1](https://example.com) is a link, not a citation.\n'
                        '```\n- Example task. [1]\n```\n')
    page += '\n- [W1] https://example.com\n'
    assert page_review.agent_threads(page.replace('\n', newline)) == TASKS


def test_moving_agent_threads_preserves_fenced_sections_and_identical_examples(owner_page):
    _, _, _, page, _ = owner_page
    example = '```\n## Who they are\n- Example profile.\n## Open threads\n' + TASKS[0] + '\n```\n'
    fenced_task = '```\n' + TASKS[0] + '\n```\n'
    page = page.replace('## Open threads\n' + TASKS[0], '## Open threads\n' + fenced_task + TASKS[0])
    page = page.replace('# Avery Lin\n', '# Avery Lin\n' + example)
    moved = page_review.move_agent_threads(page)
    assert example in moved and fenced_task in moved
    assert page_review.agent_threads(moved) == []
    visible = page_review.prose(moved)
    who = visible.split('## Who they are\n')[1].split('\n## ', 1)[0]
    assert who.strip().endswith('\n'.join(TASKS))
    assert moved.count(TASKS[0]) == page.count(TASKS[0])


@pytest.mark.parametrize('boundary', ['## Other notes', 'Investigation: mapped today'])
def test_agent_threads_does_not_resolve_citations_outside_sources(boundary):
    page = ('# Avery Lin\n\n## Open threads\n- Research hotels. [1][2]\n'
            '\n## Sources\n- [1] codex:avery:1\n\n' + boundary + '\n- [2] claude-code:avery:2\n')
    assert page_review.agent_threads(page) == []


@pytest.mark.parametrize('stage,repairs,expected', [
    ('investigate', 2, [True, True, False]),
    ('investigate', 0, [False]),
    ('enrich', 2, [False]),
    ('muse', 2, [False]),
    ('maintain', 2, [False]),
])
def test_owner_threads_request_only_nonfinal_investigation_repairs(
        owner_page, tmp_path, monkeypatch, stage, repairs, expected):
    from connectonion.rem import project_claim_review

    notebook, record, original, page, items = owner_page
    candidate = tmp_path / 'candidate.md'
    candidate.write_text(page)
    monkeypatch.setattr(project_claim_review, 'review', lambda *a, **kw: ({'verdict': 'pass'}, {}))
    promote, attempts, prompts = runner._promote_candidate, [], []

    def tracked(*args, **kwargs):
        attempts.append(kwargs['ask_quotes'])
        return promote(*args, **kwargs)

    monkeypatch.setattr(runner, '_promote_candidate', tracked)

    def repair(workdir, prompt, config, stage):
        errors = json.loads((tmp_path / 'review.json').read_text())['errors']
        assert errors == [
            f'Open thread rests only on coding sessions: {line[:160]} -- a task the user gave a coding '
            'agent is work in progress: move it to Who they are, or cite the person it is owed to'
            for line in TASKS]
        prompts.append(prompt)
        return {}

    result = {}
    runner.promote_with_repairs(notebook, record, candidate, original, items, tmp_path, result,
                               workdir=tmp_path, config={}, stage=stage, repairs=repairs, run=repair)
    assert attempts == expected
    assert len(prompts) == result['repairs'] == sum(expected)
    saved = notebook.read(record)
    who = saved.split('## Who they are\n')[1].split('\n## ', 1)[0]
    threads = saved.split('## Open threads\n')[1].split('\n## ', 1)[0]
    assert who.strip().endswith('\n'.join(TASKS))
    assert threads.strip() == OWED
    assert all(saved.count(line) == 1 for line in TASKS)
    assert page_review._listed_sources(saved) == page_review._listed_sources(page)


@pytest.mark.parametrize('last_resort', [False, True])
def test_final_owner_promotion_moves_all_tasks_and_leaves_unknown(owner_page, tmp_path, last_resort):
    notebook, record, original, page, items = owner_page
    candidate = tmp_path / 'candidate.md'
    candidate.write_text(page.replace(OWED + '\n', ''))
    runner._promote_candidate(notebook, record, candidate, original, items, tmp_path, None,
                              last_resort=last_resort, ask_quotes=last_resort)
    saved = notebook.read(record)
    assert '## Open threads\n- Unknown\n' in saved
    assert saved.index(TASKS[0]) < saved.index('## Open threads')
    assert saved.index(TASKS[1]) < saved.index('## Open threads')
    assert 'Open thread rests only on coding sessions:'.startswith(runner.SALVAGEABLE)


def test_other_person_keeps_session_threads_even_when_named_like_owner(owner_page, tmp_path):
    notebook, record, original, page, items = owner_page
    write_json(state_path(notebook.root, 'map.json'), {'owner': {'record': 'people/theo.md'}})
    candidate = tmp_path / 'candidate.md'
    candidate.write_text(page)
    runner._promote_candidate(notebook, record, candidate, original, items, tmp_path, None, ask_quotes=True)
    assert page_review.agent_threads(notebook.read(record)) == TASKS


def insight_page(insight, kind='codex', sources=4):
    return ('# Avery Lin\n\n## History\n'
            + ''.join(f'- “Please send draft {n}” [1]\n' for n in range(10))
            + '\n## Insight\n'
            + ''.join(f'- Pilot finding {n}. [1][2]\n' for n in range(insight))
            + '\n## Sources\n'
            + ''.join(f'- [{n + 1}] {kind}:avery:{n} — 2026-10-{n % 2 + 1:02d}\n'
                      for n in range(sources)))


@pytest.mark.parametrize('insight', [1, 2, 3])
@pytest.mark.parametrize('kind', ['codex', 'claude-code', 'gmail'])
def test_owner_insight_floor_counts_all_source_kinds(insight, kind):
    page = insight_page(insight, kind)
    expected = (10, 4, insight) if insight < 3 else None
    assert inv.falls_short(page, min_insight=3) == expected
    assert inv.falls_short(page) == ((10, 4, insight) if kind == 'gmail' and insight < 2 else None)
    assert inv.falls_short(insight_page(insight, kind, sources=3), min_insight=3) is None


@pytest.mark.parametrize('owner,kind,insight,called', [
    (True, 'codex', 1, True), (True, 'codex', 2, True), (True, 'codex', 3, False),
    (True, 'claude-code', 2, True), (True, 'gmail', 2, True),
    (False, 'codex', 1, False), (False, 'gmail', 1, True), (False, 'gmail', 2, False),
])
def test_quote_pass_uses_map_owner_record_and_passes_insight_target(
        tmp_path, owner, kind, insight, called):
    notebook, record = Notebook(tmp_path), 'people/avery.md'
    write_json(state_path(tmp_path, 'map.json'), {'owner': {'record': record if owner else 'people/theo.md'}})
    notebook.write(record, insight_page(insight, kind))
    turns = []
    originals = [{'source': f'{kind}:avery:{n}', 'text': f'Please send draft {n}'} for n in range(4)]

    def run(book, items, config, stage):
        turns.append(items)
        target = 3 if owner else 2
        assert f'Bring Insight to {target}–4 bullets' in items[1]['text']
        assert items[2:] == originals
        book.write(record, insight_page(target, kind))
        return {'changed': [record]}

    out = inv.quote_pass(run, notebook, record, [originals], {})
    assert bool(turns) == called
    if called:
        assert out['counts']['insight'] == [insight, 3 if owner else 2]
    else:
        assert out is None
