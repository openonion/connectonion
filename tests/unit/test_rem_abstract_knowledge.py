"""Abstract learns across notebook pages without replacing Investigate's work."""

import json
import re
from pathlib import Path

import pytest
from typer.testing import CliRunner

from connectonion.cli.main import app
from connectonion.rem import runner, translate
from connectonion.rem.config import default_config, prepare
from connectonion.rem.files import Notebook, read_json

pytestmark = pytest.mark.usefixtures('rem_clock')
WORDS = 'Use Markdown rather than a database for inspectability.'
SOURCE = 'codex:fixture:7'
KNOWLEDGE = f'''# Inspectable storage makes recovery possible

Plain pages made diagnosis possible across the storage choice and the trial.
“{WORDS}” [1]
“Keep pages inspectable.” [2]

## Drawn from
- [Storage choice](../sessions/fixture.md)
- [Storage trial](../projects/fixture.md)

## Sources
- [1] {SOURCE} — originating page: `sessions/fixture.md`.
- [2] codex:fixture:8 — originating page: `projects/fixture.md`.
'''
DECISION = f'# Storage choice\n\n“{WORDS}” [1]\n\n## Sources\n- [1] {SOURCE}\n'


@pytest.fixture
def book(tmp_path, monkeypatch):
    home = tmp_path / 'home'
    home.mkdir()
    monkeypatch.setenv('HOME', str(home))
    monkeypatch.setenv('TMPDIR', str(home))
    root = tmp_path / 'notebook'
    prepare(root)
    notebook = Notebook(root)
    notebook.write('sessions/fixture.md', f'# Session\n\n## Decisions\n- “{WORDS}” [1]\n\n## Sources\n- [1] {SOURCE}\n')
    notebook.write('projects/fixture.md', '# Project\n\n## Key decisions\n- “Keep pages inspectable.” [1]\n\n## Sources\n- [1] codex:fixture:8\n')
    return notebook


def task(book, *, native=True):
    from connectonion.rem.captured_decisions import material
    return runner.prepare(book, material(book), default_config(), stage='abstract',
                          directory=book.root / 'task', native=native)


@pytest.mark.parametrize('native', [True, False])
def test_abstract_promotes_knowledge_through_existing_review(book, native):
    prepared = task(book, native=native)
    Notebook(Path(prepared['task_root'])).write('knowledge/storage-recovery.md', KNOWLEDGE)
    assert runner.check(prepared, {}, native=native) == []
    assert WORDS in book.read('knowledge/storage-recovery.md')
    review = read_json(Path(prepared['directory']) / 'review.json', {})
    assert review['accepted'] == ['knowledge/storage-recovery.md']
    assert review['refused'] == []


@pytest.mark.parametrize('native', [True, False])
def test_abstract_refuses_overwriting_investigate_knowledge(book, native):
    book.stub_topic('knowledge/existing.md', 'Storage')
    original = book.read('knowledge/existing.md')
    prepared = task(book, native=native)
    Notebook(Path(prepared['task_root'])).write('knowledge/existing.md', KNOWLEDGE)
    if native:
        with pytest.raises(runner.RunFailed, match='append'):
            runner.check(prepared, {}, native=native)
    else:
        refusals = runner.check(prepared, {}, native=native)
        assert any('append' in error for row in refusals for error in row['errors'])
    assert book.read('knowledge/existing.md') == original


@pytest.mark.parametrize('native', [True, False])
def test_abstract_appends_experience_without_changing_one_original_byte(book, native):
    book.stub_topic('knowledge/existing.md', 'Storage')
    original = book.read('knowledge/existing.md').replace('## Sources\n', '## Sources\n- [7] codex:old:3\n')
    book.write('knowledge/existing.md', original)
    prepared = task(book, native=native)
    appendix = '\n## Settled experience: recovery\n' + KNOWLEDGE.split('\n', 1)[1].replace('## ', '### ')
    output = Notebook(Path(prepared['task_root']))
    output.write('knowledge/existing.md', original + appendix)
    assert runner.check(prepared, {}, native=native) == []
    saved = book.read('knowledge/existing.md')
    assert saved.startswith(original)
    assert '## Settled experience: recovery' in saved[len(original):]
    assert '### Sources\n- [1] ' + SOURCE in saved[len(original):]


SECTION = f'''
## Settled experience: recovery
Recovery reads the plain page first.
“Keep pages inspectable.” [3]
“{WORDS}” [4]

### Drawn from
- [Storage choice](../sessions/fixture.md)
- [Storage trial](../projects/fixture.md)
'''
DEFINITIONS = f'- [3] codex:fixture:8 — originating page: `projects/fixture.md`.\n- [4] {SOURCE} — originating page: `sessions/fixture.md`.\n'


def one_sources_last(saved, original):
    """The page #3097 asks the night for: every earlier line kept, the new section above one closing Sources."""
    head, _, sources = original.partition('\n## Sources\n')
    assert saved.startswith(head) and len(re.findall(r'(?m)^#{2,3} Sources$', saved)) == 1
    after_head, _, after_sources = saved.partition('\n## Sources\n')
    assert '## Settled experience: recovery' in after_head[len(head):] and '### Drawn from' in after_head[len(head):]
    assert after_sources == sources + DEFINITIONS
    assert not re.search(r'(?m)^#', after_sources)


@pytest.mark.parametrize('native', [True, False])
def test_a_section_added_to_a_page_that_ends_with_sources_goes_above_them(book, native):
    book.write('knowledge/storage.md', KNOWLEDGE)
    prepared = task(book, native=native)
    head, marker, sources = KNOWLEDGE.partition('\n## Sources\n')
    Notebook(Path(prepared['task_root'])).write('knowledge/storage.md', head + '\n' + SECTION + marker + sources + DEFINITIONS)
    assert runner.check(prepared, {}, native=native) == []
    one_sources_last(book.read('knowledge/storage.md'), KNOWLEDGE)


def test_an_appendix_written_after_the_closing_sources_is_folded_into_the_one_list(book):
    book.write('knowledge/storage.md', KNOWLEDGE)
    prepared = task(book)
    Notebook(Path(prepared['task_root'])).write('knowledge/storage.md', KNOWLEDGE + SECTION + '\n### Sources\n' + DEFINITIONS)
    assert runner.check(prepared, {}, native=True) == []
    one_sources_last(book.read('knowledge/storage.md'), KNOWLEDGE)


@pytest.mark.parametrize('change,reason', [
    (lambda text: text.replace('Plain pages made', 'Plain pages once made'), 'preserve'),
    (lambda text: text.replace(f'- [1] {SOURCE}', '- [1] codex:fixture:8'), 'preserve'),
    (lambda text: text.replace('[3]', '[1]').replace('[4]', '[2]'), 'fresh citation numbers'),
])
def test_a_section_added_above_sources_may_not_change_what_was_there(book, change, reason):
    book.write('knowledge/storage.md', KNOWLEDGE)
    prepared = task(book)
    head, marker, sources = KNOWLEDGE.partition('\n## Sources\n')
    Notebook(Path(prepared['task_root'])).write('knowledge/storage.md', change(head + '\n' + SECTION + marker + sources + DEFINITIONS))
    with pytest.raises(runner.RunFailed, match=reason):
        runner.check(prepared, {}, native=True)
    assert book.read('knowledge/storage.md') == KNOWLEDGE


def test_the_skill_says_a_knowledge_page_ends_with_one_sources_and_shows_it():
    skill = (runner.useful_skills_dir() / 'rem-abstract/SKILL.md').read_text(encoding='utf-8')
    lift = skill.split('## Knowledge lift', 1)[1]
    assert 'ends with one `## Sources`' in lift and 'above `## Sources`' in lift
    for example in re.findall(r'(?s)```markdown\n(.*?)```', lift):  # every example ends with its one Sources list
        assert example.count('\n## Sources\n') == 1 and '### Sources' not in example
        assert not re.search(r'(?m)^#', example.partition('\n## Sources\n')[2])


@pytest.mark.parametrize('body,reason', [
    (KNOWLEDGE.replace('- [Storage trial](../projects/fixture.md)\n', ''), 'two notebook pages'),
    (KNOWLEDGE.replace('../projects/fixture.md', '../projects/missing.md'), 'two notebook pages'),
    (KNOWLEDGE.replace('../projects/fixture.md', '../sessions/fixture.md'), 'two notebook pages'),
    (KNOWLEDGE.replace('## Drawn from', '## Reading'), 'Drawn from'),
    (KNOWLEDGE.replace(f'“{WORDS}” [1]', 'A paraphrase.').replace('“Keep pages inspectable.” [2]', 'Another paraphrase.'), "owner's words"),
    (KNOWLEDGE.replace(WORDS, 'An invented quote.').replace('Keep pages inspectable.', 'Another invented quote.'), "owner's words"),
    (KNOWLEDGE.replace(SOURCE, 'codex:invented:99'), 'source'),
])
def test_abstract_knowledge_is_refused_by_existing_page_review(book, body, reason):
    prepared = task(book)
    output = Notebook(Path(prepared['task_root']))
    output.write('decisions/storage.md', DECISION)
    output.write('knowledge/invalid.md', body)
    refusals = runner.check(prepared, {}, native=True)
    assert book.exists('decisions/storage.md') and not book.exists('knowledge/invalid.md')
    assert reason in ' '.join(refusals[0]['errors'])
    review = read_json(Path(prepared['directory']) / 'review.json', {})
    assert review['accepted'] == ['decisions/storage.md']
    assert review['refused'][0]['record'] == 'knowledge/invalid.md'


def test_abstract_knowledge_can_draw_from_decision_written_this_round(book):
    prepared = task(book)
    output = Notebook(Path(prepared['task_root']))
    output.write('decisions/storage.md', DECISION)
    output.write('knowledge/storage.md', KNOWLEDGE.replace('../sessions/fixture.md', '../decisions/storage.md'))
    assert runner.check(prepared, {}, native=True) == []
    assert book.exists('knowledge/storage.md')


def test_abstract_knowledge_rejects_unheaded_append_and_citation_reuse(book):
    book.write('knowledge/existing.md', '# Storage\n\n“Old words.” [1]\n\n## Sources\n- [1] codex:old:3\n')
    original = book.read('knowledge/existing.md')
    prepared = task(book)
    output = Notebook(Path(prepared['task_root']))
    for appendix in ['\nSome more text.\n', '\n## Experience\n' + KNOWLEDGE.split('\n', 1)[1].replace('## ', '### ')]:
        output.write('knowledge/existing.md', original + appendix)
        with pytest.raises(runner.RunFailed):
            runner.check(prepared, {}, native=True)
        assert book.read('knowledge/existing.md') == original


def test_abstract_knowledge_concurrent_edit_is_preserved(book):
    prepared = task(book)
    Notebook(Path(prepared['task_root'])).write('knowledge/storage.md', KNOWLEDGE)
    book.write('knowledge/storage.md', '# A concurrent Investigate page\n')
    with pytest.raises(runner.RunFailed, match='changed during abstraction'):
        runner.check(prepared, {}, native=True)
    assert book.read('knowledge/storage.md') == '# A concurrent Investigate page\n'


def test_abstract_reports_three_counts_and_keeps_decisions_status(book, monkeypatch):
    from connectonion.rem import decisions

    def model(workspace, prompt, config, stage, **options):
        output = Notebook(next(workspace.glob('abstract-*/material.json')).parent / 'notebook')
        output.write('decisions/storage.md', DECISION)
        output.write('knowledge/storage.md', KNOWLEDGE)
        output.write('principles/inspection.md', '# Prefer inspection\n')
        return {'result': 'Learned from the notebook'}

    monkeypatch.setattr(runner, 'run_task', model)
    cli = CliRunner()
    result = cli.invoke(app, ['rem', '--root', str(book.root), '--json', 'abstract', '--rounds', '1'])
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)['data']
    assert data['pages'] == {'decisions': 1, 'knowledge': 1, 'principles': 1}
    assert data['written'] == 3 and 'knowledge/storage.md' in data['rounds'][0]['changed']
    again = cli.invoke(app, ['rem', '--root', str(book.root), 'abstract', '--rounds', '1'])
    assert 'Pages: 1 decisions · 1 knowledge · 1 principles' in again.output
    status = cli.invoke(app, ['rem', '--root', str(book.root), 'status'])
    lines = status.output.splitlines()
    line = next(index for index, line in enumerate(lines) if line.startswith('Abstract:'))
    # The counts are the sentence's last clause, on its own line where the sentence would pass 80 columns.
    assert '1 decisions · 1 knowledge · 1 principles' in ' '.join(lines[line:line + 2])
    status_json = cli.invoke(app, ['rem', '--root', str(book.root), '--json', 'status'])
    abstract = next(row for row in json.loads(status_json.output)['data']['stages'] if row['name'] == 'Abstract')
    assert abstract['pages'] == data['pages']
    assert 'knowledge' not in decisions.status(book.root)


def test_abstract_knowledge_joins_translation_discovery_outside_census(book, monkeypatch):
    book.write('knowledge/storage.md', KNOWLEDGE)
    monkeypatch.setattr('connectonion.rem.census.pages', lambda root: {})
    assert 'knowledge/storage.md' in translate.written_pages(book.root)


@pytest.mark.parametrize('with_stamp', [False, True])
def test_abstract_appended_knowledge_is_translated_with_all_sources_preserved(book, with_stamp):
    original = '# Storage\n\nOriginal finding. [7]\n\n## Sources\n- [7] codex:old:3\n'
    if with_stamp:
        original += '\nInvestigation: mapped 2026-11-01 · investigated 2026-11-02\n'
    appendix = '\n## Settled experience: recovery\n' + KNOWLEDGE.split('\n', 1)[1].replace('## ', '### ')
    text = original + appendix
    book.write('knowledge/storage.md', text)
    directory = book.root / 'translation'
    directory.mkdir()
    task = translate.prepare(book.root, 'knowledge/storage.md', 'zh', directory=directory)
    assert 'Plain pages made diagnosis possible' in task['prose']
    assert 'codex:old:3' not in task['prose'] and SOURCE not in task['prose']
    output = task['prose'].replace('Plain pages made diagnosis possible', '纯文本页面让诊断成为可能')
    result = translate.check(task, {'result': output})
    assert '纯文本页面让诊断成为可能' in result
    assert '- [7] codex:old:3\n' in result and '- [1] ' + SOURCE in result
    assert ('Investigation:' in result) == with_stamp
    assert translate.cached(book.root, 'knowledge/storage.md', 'zh') == result
    assert book.read('knowledge/storage.md') == text
    path = translate.translation_path(book.root, 'knowledge/storage.md', 'zh')
    path.write_text(path.read_text().replace(SOURCE, 'codex:tampered:99'))
    assert translate.cached(book.root, 'knowledge/storage.md', 'zh') is None


@pytest.mark.parametrize('kind', ['new', 'appended', 'new_with_topic_heading'])
def test_abstract_knowledge_reader_shows_learning_once_and_gathers_appendix_sources(kind):
    """The entry page's model (#3097): the learning is text, Drawn from is links, every Sources block is one list."""
    import re
    from tests.unit.test_rem_reader import _run_reader_js
    from connectonion.rem.reader import TEMPLATE
    page = TEMPLATE.read_text()
    functions = '\n'.join(re.search(r'function ' + name + r'\(.*?\n\}', page, re.S).group(0)
                          for name in ['entryParse', 'entryNumbers', 'entryModel', 'sourceId'])
    text = KNOWLEDGE
    if kind == 'new_with_topic_heading':
        text = text.replace('Plain pages', '## What it is\nPlain pages', 1)
    if kind == 'appended':
        text = '# Storage\n\n## What it is\nExisting topic. [7]\n\n## Sources\n- [7] codex:old:3\n'
        text += '\n## Settled experience: recovery\n' + KNOWLEDGE.split('\n', 1)[1].replace('## ', '### ')
    body = text.split('\n', 1)[1]
    result = _run_reader_js(functions + '\nconsole.log(JSON.stringify(entryModel(' + json.dumps(body) + ')));')
    read = '\n'.join(section['text'] for section in result['sections'])
    assert read.count('Plain pages made diagnosis possible') == 1
    assert 'Sources' not in read and 'Drawn from' not in read
    drawn = [link for section in result['sections'] for link in section['drawn']]
    assert drawn == ['[Storage choice](../sessions/fixture.md)', '[Storage trial](../projects/fixture.md)']
    sources = [source['text'].split(' ')[0] for source in result['sources']]
    assert sources == (['codex:old:3'] if kind == 'appended' else []) + [SOURCE, 'codex:fixture:8']
    if kind == 'appended':  # one list, numbered on: the appendix's [1] is the page's second source
        assert [source['n'] for source in result['sources']] == ['1', '2', '3']
        assert 'Existing topic. [1]' in read and '” [2]' in read and '” [3]' in read


def test_abstract_help_plain_contract_and_offline_audit():
    from connectonion.cli.audit import Page, check
    result = CliRunner().invoke(app, ['rem', 'abstract', '--help'])
    assert result.exit_code == 0, result.output
    for text in ['decisions, knowledge, and principles, in that order', 'at least two pages',
                 'at least three decisions', 'Flags:', '--rounds N', '--help',
                 'Example:  co rem abstract --rounds 2', 'Next:     co rem list decisions']:
        assert text in result.output
    assert result.output.count('Example:') == 1
    assert 'Legacy session quotes' not in result.output and 'VERDICT' not in result.output
    assert check('co rem abstract', Page(0, result.output), {}) == []
