"""A page's quotes are the speaker's words, and review settles what it can.

Real cases from the 1.9.2b3 first run (2026-10-10), anonymised where they
name people: a fee quoted as “8% of gross revenue” where the owner wrote
"8% of net booking revenue"; Chinese instructions put in English inside
quotation marks; a person page refused on every pass for one heading glued
to a paragraph.
"""

import json
from pathlib import Path

import pytest

from connectonion.rem import runner
from connectonion.rem.config import prepare
from connectonion.rem.files import Notebook
from connectonion.rem.page_review import drop_claims, merge_duplicate_sections, misquoted, validate

NOWHERE = Path('/nonexistent-notebook')


def page(lines: str, sources: str) -> str:
    return f'# Atlas\n\n{lines}\n\n## Sources\n{sources}'


def test_a_quote_copied_from_its_source_passes_across_line_wraps_and_punctuation():
    text = page('- 2026-10-01 — Ody asked: “可以放在 Connect 页面上，我们自己再转发一下也可以。” [1]\n'
                '- She signed off “Best.” and wrote “sounds great,” [1]',
                '- [1] gmail:abc — 2026-10-01\n')
    items = [{'source': 'gmail:abc', 'text': 'Hi,\n> earlier\n可以放在 Connect 页面上，\n我们自己再转发一下也可以。\n'
                                             'That sounds great\nBest'}]
    assert misquoted(NOWHERE, 'people/ody.md', text, items) == []


def test_a_paraphrase_or_translation_inside_quotation_marks_is_refused():
    text = page('- Fee: “8% of gross revenue” [1]\n- The user said it was “not right” [2]',
                '- [1] codex:s:1 — 2026-09-01\n- [2] codex:s:2 — 2026-10-15\n')
    items = [{'source': 'codex:s:1', 'text': '* 8% of net booking revenue'},
             {'source': 'codex:s:2', 'text': '他说有一个 websocket 有一个没有搞对'}]
    errors = misquoted(NOWHERE, 'projects/atlas.md', text, items)
    assert errors == ['Quote is not in its cited source: “8% of gross revenue”',
                      'Quote is not in its cited source: “not right”']


def test_ellipses_join_parts_that_appear_in_order():
    text = page('- “we will send the deck … before Friday” [1]', '- [1] gmail:abc — 2026-10-01\n')
    items = [{'source': 'gmail:abc', 'text': 'we will send the deck, with the numbers, before Friday'}]
    assert misquoted(NOWHERE, 'people/x.md', text, items) == []
    backwards = page('- “before Friday … we will send the deck” [1]', '- [1] gmail:abc — 2026-10-01\n')
    assert misquoted(NOWHERE, 'people/x.md', backwards, items)


def test_a_quote_whose_original_is_not_here_is_left_to_the_audit():
    text = page('- “anything at all” [1]', '- [1] gmail:unread — 2026-10-01\n')
    assert misquoted(NOWHERE, 'people/x.md', text, []) == []


def test_skill_pages_quote_their_runs_and_are_not_checked_here():
    text = page('- “META SAM” [1]', '- [1] gmail:abc — 2026-10-01\n')
    assert misquoted(NOWHERE, 'skills/catalog/cover.md', text, [{'source': 'gmail:abc', 'text': 'x'}]) == []


def test_drop_claims_removes_the_line_and_reports_claims_it_cannot_find():
    text = ('# X\n\n## Facts\n- Phone: 0400 000 000 [1]\n\n## Insight\n- Now: true thing [2]\n'
            '- Now: false thing [1]\n\n## Sources\n- [1] gmail:a — 2026-10-01\n- [2] gmail:b — 2026-10-01\n')
    kept, unlocated = drop_claims('people/x.md', text, ['false thing', '0400 000 000', 'not on the page'])
    assert '- Now: false thing' not in kept and '- Now: true thing [2]' in kept
    assert '- Phone: Unknown' in kept
    assert unlocated == ['not on the page']


def test_a_glued_heading_and_a_repeated_section_are_merged_not_refused():
    text = ('# Hamish\n\nLead [1].\n\n## Facts\n- Email: h@example.com\n\n## Who they are\n'
            'He leads the program [1]. ## Our relationship\n- Colleagues [1]\n\n'
            '## Uncertainties\n- Unknown\n\n## Uncertainties\n- Whether he stays [1]\n\n'
            '## Sources\n- [1] gmail:a — 2026-10-01\n')
    merged = merge_duplicate_sections('people/hamish.md', text)
    assert 'program [1].\n\n## Our relationship\n- Colleagues [1]' in merged
    assert merged.count('## Uncertainties') == 1 and '- Whether he stays [1]' in merged
    assert not [e for e in validate('people/hamish.md', merged, '', []) if 'occur once' in e or 'Duplicate' in e]


def _person(tmp_path):
    prepare(tmp_path)
    notebook = Notebook(tmp_path)
    notebook.stub_person('people/ody.md', 'Ody', ['ody@example.com'], email='ody@example.com')
    old = notebook.read('people/ody.md')
    written = (old.replace('- Unknown — not investigated yet', '- Unknown')
               .replace('## Open threads\n- Unknown',
                        '## Open threads\n- 2026-10-01 — Ody asked: “send the deck by Friday” [1] — open\n'
                        '- 2026-10-02 — Ody offered: “I can intro you to Sam” [1] — open')
               .replace('- (none yet)', '- [1] gmail:abc — 2026-10-01'))
    items = [{'role': 'page', 'record': 'people/ody.md', 'text': old},
             {'source': 'gmail:abc', 'text': 'Could you send the deck by Friday? Happy to introduce Sam.'}]
    return notebook, old, written, items


def test_review_gives_the_writer_turns_to_fix_a_misquote_then_keeps_the_sound_lines(tmp_path, monkeypatch):
    notebook, old, written, items = _person(tmp_path)
    candidate = tmp_path / 'candidate.md'
    candidate.write_text(written)
    repairs = []
    monkeypatch.setattr(runner, 'run_task', lambda *args: repairs.append(args[1]) or {'usage': {}})
    result = {'usage': {'input_tokens': 5}}
    runner.promote_with_repairs(notebook, 'people/ody.md', candidate, old, items, tmp_path, result,
                                workdir=tmp_path, config={}, stage='investigate')
    assert len(repairs) == runner.MAX_REPAIRS and '“I can intro you to Sam”' in repairs[0]
    saved = notebook.read('people/ody.md')
    assert '“send the deck by Friday”' in saved and 'intro you to Sam' not in saved


def test_review_refuses_what_it_cannot_settle(tmp_path, monkeypatch):
    notebook, old, written, items = _person(tmp_path)
    candidate = tmp_path / 'candidate.md'
    candidate.write_text(written.replace('# Ody', '# Ody\n\n# Second title'))
    monkeypatch.setattr(runner, 'run_task', lambda *args: {'usage': {}})
    with pytest.raises(runner.RunFailed, match='exactly one page title'):
        runner.promote_with_repairs(notebook, 'people/ody.md', candidate, old, items, tmp_path, {},
                                    workdir=tmp_path, config={}, stage='investigate')
    assert notebook.read('people/ody.md') == old


def test_an_audit_finding_goes_with_its_line_after_the_repairs(tmp_path, monkeypatch):
    notebook, old, written, items = _person(tmp_path)
    candidate = tmp_path / 'candidate.md'
    candidate.write_text(written.replace('“I can intro you to Sam”', '“Happy to introduce Sam”'))
    finding = {'claim': 'Ody offered: “Happy to introduce Sam”', 'issue': 'Sam is not named as an intro',
               'evidence': 'x', 'required_correction': 'remove'}
    monkeypatch.setattr(runner, 'run_claim_task', lambda *_args: {
        'result': json.dumps({'verdict': 'FAIL', 'findings': [finding]}), 'usage': {}})
    monkeypatch.setattr(runner, 'run_task', lambda *args: {'usage': {}})
    runner.promote_with_repairs(notebook, 'people/ody.md', candidate, old, items, tmp_path, {},
                                workdir=tmp_path, config={}, stage='investigate')
    saved = notebook.read('people/ody.md')
    assert 'introduce Sam' not in saved and '“send the deck by Friday”' in saved
