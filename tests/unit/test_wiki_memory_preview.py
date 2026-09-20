"""Record provenance, preserve disagreement, and fail before accepted-page mutation."""
import json

import pytest

from connectonion.wiki.files import Notebook, WikiError, write_json
from connectonion.wiki import reflections, reviews, inquiry


@pytest.fixture
def root(tmp_path):
    Notebook(tmp_path).write('projects/a.md', '# A\n')
    Notebook(tmp_path).write('projects/b.md', '# B\n')
    return tmp_path


def test_correction_and_later_change_retain_history(root):
    first = reflections.add(root, 'projects/a.md', 'Prototype', author='user', basis='Release is unverified',
                            previous='Launched', kind='correction', applies='Before June')
    second = reflections.add(root, 'projects/a.md', 'Launched in July', author='agent', basis='Release tag',
                             kind='change', sources=['release:1'], supersedes=[first['id']])
    context = reflections.context(root, 'projects/a.md')
    assert len(context) == 2
    assert all(r['status'] == 'asserted' for r in reflections.records(root))
    compact = reflections.compress(root, 'projects/a.md')
    restored = [dict(zip(compact['fields'], row)) for row in compact['rows']]
    assert restored == reflections.records(root, 'projects/a.md')
    assert second['supersedes'] == [first['id']]
    assert len(reflections.records(root)) == 2


def test_supersession_cannot_cross_subject(root):
    first = reflections.add(root, 'projects/a.md', 'A', author='user', basis='Observed')
    with pytest.raises(WikiError):
        reflections.add(root, 'projects/b.md', 'B', author='user', basis='Observed', supersedes=[first['id']])


def test_rejected_connection_does_not_reappear(root):
    row = reviews.propose(root, 'link', ['projects/a.md', 'projects/b.md'], 'Same constraint?', 'Both mention costs')
    reviews.decide(root, row['id'], 'no', author='user', response='Different constraints')
    again = reviews.propose(root, 'link', ['projects/a.md', 'projects/b.md'], 'Same constraint?', 'Both mention costs')
    assert again['status'] == 'rejected'
    assert len(reviews.listing(root)) == 1
    with pytest.raises(WikiError):
        reviews.decide(root, row['id'], 'yes', author='agent')


def test_question_answer_preserves_basis(root):
    row = reviews.propose(root, 'question', ['projects/a.md'], 'What changed?', 'Earlier decision')
    with pytest.raises(WikiError):
        reviews.decide(root, row['id'], 'yes', author='user')
    reviews.decide(root, row['id'], 'answer', author='user', response='Budget changed')
    assert 'Budget changed' in reviews.context(root, 'projects/a.md')[0]['text']


def test_inquiry_preserves_overturned_and_unresolved(root):
    directory = root / 'task'
    directory.mkdir()
    items = [{'source': 'mail:1', 'text': 'Delay is ours, not theirs'}]
    write_json(directory / 'material.json', items)
    config = {'runner': 'coai', 'model': 'ollama/local'}
    def execute(directory, prompt, cfg, stage):
        assert cfg['model'] == 'ollama/local'
        if not (directory / 'plan.json').exists():
            write_json(directory / 'plan.json', {'questions': [{'question': 'Why delay?', 'hypothesis': 'Their delay',
                       'alternative': 'Our delay', 'would_change': 'An unanswered action on us'}]})
        else:
            write_json(directory / 'synthesize.json', {'findings': [
                {'question': 'Why delay?', 'before': 'Their delay', 'after': 'Our delay', 'reason': 'Our action outstanding',
                 'status': 'overturned', 'sources': ['mail:1']},
                {'question': 'Next date?', 'before': 'Unknown', 'after': 'Unknown', 'reason': 'No date in evidence',
                 'status': 'unresolved', 'sources': []}], 'method_review': {'proposed_changes': ['Check both sides']}})
        return {'usage': {'input_tokens': 10, 'output_tokens': 5}}
    result = inquiry.run(root, directory, items, config, execute)
    assert result['usage']['input_tokens'] == 20
    assert json.loads((directory / 'method-review.json').read_text())['status'] == 'candidate_only'
    assert Notebook(root).read('projects/a.md') == '# A\n'


def test_inquiry_rejects_fabricated_evidence():
    with pytest.raises(WikiError):
        inquiry.validate_findings({'findings': [{'status': 'supported', 'question': 'Q', 'before': '', 'after': '',
            'reason': '', 'sources': ['invented']}], 'method_review': {}}, {'real'})


def test_capture_survives_source_removal_and_filters_injection(root):
    from connectonion.wiki.capture import capture, pending
    path = root / 'rollout-test.jsonl'
    rows = [{'type': 'session_meta', 'payload': {'id': 'abc', 'cwd': '/project'}}]
    def message(text, **extra):
        return {'type': 'response_item', 'timestamp': '2026-09-20T00:00:00Z',
                'payload': {'type': 'message', 'role': 'user',
                            'content': [{'type': 'input_text', 'text': text}], **extra}}
    rows += [message('We chose the local provider'), message('Injected', internal_chat_message_metadata_passthrough={})]
    path.write_text(''.join(json.dumps(row) + '\n' for row in rows))
    assert capture(root, path, 'codex')['captured'] == 1
    assert capture(root, path, 'codex')['captured'] == 0
    path.unlink()
    items = pending(root, [], 20, 200000)
    assert len(items) == 1 and items[0]['text'] == 'We chose the local provider'
    assert pending(root, [items[0]['source']], 20, 200000) == []


def test_cli_reflection_review_and_routing(root):
    from typer.testing import CliRunner
    from connectonion.cli.main import app
    runner = CliRunner()
    prefix = ['wiki', '--root', str(root), '--json']
    commands = [
        ['reflect', 'projects/a.md', 'Prototype only', '--author', 'user', '--basis', 'Not released'],
        ['reflections', 'projects/a.md', '--compact'],
        ['propose', 'link', 'projects/a.md', 'Shared constraint?', '--related', 'projects/b.md', '--basis', 'Costs'],
        ['review'],
        ['route', 'plan', '--runner', 'coai', '--model', 'ollama/local'],
    ]
    for args in commands:
        result = runner.invoke(app, prefix + args)
        assert result.exit_code == 0, result.output
        assert json.loads(result.stdout)['ok']


def test_invalid_plan_preserves_page_and_usage(root):
    from connectonion.wiki.runner import RunFailed
    directory = root / 'bad-task'
    directory.mkdir()
    def execute(*args):
        write_json(directory / 'plan.json', {'questions': []})
        return {'usage': {'input_tokens': 17}}
    with pytest.raises(RunFailed) as caught:
        inquiry.run(root, directory, [], {'runner': 'coai', 'model': 'local'}, execute)
    assert caught.value.usage == {'input_tokens': 17}
    assert Notebook(root).read('projects/a.md') == '# A\n'


def test_reflection_only_sync_and_retry(root, monkeypatch):
    from connectonion.wiki.config import default_config
    from connectonion.wiki.service import _sync_locked
    row = reflections.add(root, 'projects/a.md', 'Not launched', author='user', basis='No release')
    def fail(*args, **kw):
        raise WikiError('Unavailable')
    first = _sync_locked(root, {}, {}, default_config(), fail)
    assert first['outcome'] == 'failed'
    assert not (root / '.state/progress.json').exists()
    seen = []
    def succeed(notebook, items, *args, **kw):
        seen.extend(items)
        return {'changed': [], 'usage': None}
    second = _sync_locked(root, {}, {}, default_config(), succeed)
    assert second['outcome'] == 'completed'
    assert seen[0]['source'] == 'reflection:' + row['id']
    progress = json.loads((root / '.state/progress.json').read_text())
    third = _sync_locked(root, {}, progress, default_config(), succeed)
    assert third['outcome'] == 'no_change'


def test_daily_maintains_before_one_investigation(root, monkeypatch):
    from connectonion.wiki.daily import run_daily
    from connectonion.wiki.config import prepare
    prepare(root)
    Notebook(root).write('projects/a.md', '# A\nUnknown\n')
    calls = []
    monkeypatch.setattr('connectonion.wiki.daily.subscriptions', lambda root: {})
    def maintain(root):
        calls.append('maintain')
        return {'outcome': 'no_change'}
    def investigate_one(*args, **kw):
        calls.append('investigate')
        assert kw['max_calls'] > 0
        return {'changed': [], 'usage': {'input_tokens': 1}}
    result = run_daily(root, maintain=maintain, investigate_one=investigate_one)
    assert result['outcome'] == 'completed'
    assert calls == ['maintain', 'investigate']
    again = run_daily(root, maintain=maintain, investigate_one=investigate_one)
    assert again['outcome'] == 'budget_exhausted'


def test_extraction_budget_refuses_before_any_model_call():
    from connectonion.wiki.investigate import digest_in_chunks
    from connectonion.wiki.config import default_config
    cfg = default_config()
    cfg['limits']['extract_items_per_batch'] = 1
    items = [{'text': 'One', 'source': 'a'}, {'text': 'Two', 'source': 'b'}]
    with pytest.raises(WikiError, match='budget'):
        digest_in_chunks(items, cfg, lambda *a: pytest.fail('Model invoked'), max_calls=1)
