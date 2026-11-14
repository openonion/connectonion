"""A captured quote belongs beside the choice, with definitions under Sources.

These fixtures are invented and run without source services or model calls.
"""

import re
from datetime import datetime, timezone
from pathlib import Path

import pytest

from connectonion.rem import captured_decisions, runner, service
from connectonion.rem.config import default_config, prepare
from connectonion.rem.files import Notebook, read_json
from connectonion.rem.page_review import unquoted_decisions

WORDS = 'Use flat files rather than a database so I can inspect them.'
SOURCE = 'codex:example:17'
QUOTE = f'“{WORDS}” [1]'
BODY = f'# Storage choice\n\n{QUOTE}\n\n## Why\nInspection. [1]\n\n## What it cost\nLinear search. [1]\n'
SOURCES = f'\n## Sources\n\n- [1] {SOURCE} — owner; originating page: `sessions/storage.md`.\n'
MISPLACED = BODY.replace(QUOTE, 'Use flat files. [1]') + SOURCES + f'\n  > {QUOTE}\n'
TEACHING = 'the quote is under Sources; put it in the body beside its [n]'


@pytest.fixture
def task(tmp_path, monkeypatch):
    monkeypatch.setattr(runner, 'ready', lambda config: ('', ''))
    monkeypatch.setattr(service, 'now', lambda: datetime(2026, 11, 15, tzinfo=timezone.utc))
    monkeypatch.setattr('connectonion.rem.config.local_timezone', lambda: 'UTC')
    prepare(tmp_path)
    book = Notebook(tmp_path)
    book.write('sessions/storage.md', f'# Storage\n\n## Decisions\n- {QUOTE}\n' + SOURCES)
    directory = tmp_path / '.state/tasks/abstract-placement'
    directory.mkdir(parents=True)
    return book, runner.prepare(book, captured_decisions.material(book), default_config(),
                                stage='abstract', directory=directory, native=True)


def test_sources_block_quote_is_refused_with_placement_instruction(task):
    book, prepared = task
    Notebook(Path(prepared['task_root'])).write('decisions/storage.md', MISPLACED)
    with pytest.raises(runner.RunFailed, match=re.escape(TEACHING)):
        runner.check(prepared, {}, native=True)
    assert not book.exists('decisions/storage.md')
    review = read_json(Path(prepared['directory']) / 'review.json', {})
    assert review['accepted'] == []
    assert any(TEACHING in error for error in review['refused'][0]['errors'])


def test_same_quote_moved_to_body_is_accepted(task):
    book, prepared = task
    working = Notebook(Path(prepared['task_root']))
    working.write('decisions/storage.md', MISPLACED)
    with pytest.raises(runner.RunFailed):
        runner.check(prepared, {}, native=True)
    working.write('decisions/storage.md', BODY + SOURCES)
    assert runner.check(prepared, {}, native=True) == []
    assert QUOTE in book.read('decisions/storage.md').partition('\n## Sources\n')[0]
    assert SOURCE in book.read('decisions/storage.md').partition('\n## Sources\n')[2]


@pytest.mark.parametrize('text', [BODY + SOURCES, BODY.replace(QUOTE, '> ' + QUOTE) + SOURCES])
def test_body_quote_binds_to_original_source(text):
    items = [{'role': 'captured-decisions', 'text': '## Decisions\n- ' + QUOTE + SOURCES}]
    assert unquoted_decisions(text, decision_page=True) == []
    assert captured_decisions.quote_errors(text, items) == []


@pytest.mark.parametrize('text', [
    BODY.replace(WORDS, 'Use a database instead.') + SOURCES,
    BODY.replace(WORDS, WORDS + ' Keep them portable too.') + SOURCES,
    BODY + SOURCES.replace(SOURCE, 'codex:example:99'),
    BODY.replace(QUOTE, f'“{WORDS}” The owner chose this. [1]') + SOURCES,
    BODY.replace(QUOTE, f'“{WORDS}”\n[1]') + SOURCES,
    MISPLACED,
])
def test_placement_fix_preserves_exact_quote_and_adjacent_source_checks(text):
    items = [{'role': 'captured-decisions', 'text': '## Decisions\n- ' + QUOTE + SOURCES}]
    assert captured_decisions.quote_errors(text, items)


def test_missing_quote_is_distinguished_from_misplaced_quote():
    missing = BODY.replace(QUOTE, 'Use flat files. [1]') + SOURCES
    assert "owner's words" in unquoted_decisions(missing, decision_page=True)[0]
    assert TEACHING not in unquoted_decisions(missing, decision_page=True)[0]
    fenced = missing + f'\n```markdown\n> {QUOTE}\n```\n'
    assert TEACHING not in unquoted_decisions(fenced, decision_page=True)[0]


def test_abstract_prompt_gives_body_example_and_separate_source_definition(task):
    _, prepared = task
    prompt = prepared['prompt']
    assert "Every decision must copy the owner's verbatim words into the body, immediately followed by its [n]." in prompt
    assert 'Under ## Sources, define each [n] with the original source ID; keep the originating page path as context.' in prompt
    assert 'Example body line: “Use Markdown so I can inspect the pages.” [1]' in prompt
    assert 'Example source definition under ## Sources: - [1] codex:s1:347' in prompt
    assert 'Copy the quote exactly as captured in the supplied ## Decisions or ## Key decisions; preserve its original source ID when renumbering citations.' in prompt
    assert "owner's verbatim words and original source ID under ## Sources" not in prompt


def test_shipped_skill_example_obeys_the_same_quote_contract():
    skill = runner.instructions('abstract')
    assert 'Copy the owner’s verbatim words into the body, immediately followed by its `[n]`.' in skill
    assert 'Under `## Sources`, define each `[n]` with its original source ID' in skill
    assert 'Copy the quote exactly as captured in the supplied `## Decisions` or' in skill
    example = re.search(r'```markdown\n(.*?)\n```', skill, re.S)[1]
    assert unquoted_decisions(example, decision_page=True) == []
    items = [{'role': 'captured-decisions', 'text': '## Decisions\n'
              '- “Use Markdown so I can inspect the pages.” [1]\n\n## Sources\n- [1] codex:s1:347\n'}]
    assert captured_decisions.quote_errors(example, items) == []
