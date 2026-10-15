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


@pytest.mark.parametrize('field', ['Email', 'Handles', 'Also known as'])
@pytest.mark.parametrize('claim', ['{field}: vern.chan@unsw.edu.au', 'vern.chan@unsw.edu.au'])
def test_drop_claims_keeps_uncited_fields_but_drops_a_refuted_phone(field, claim):
    """Vern Chan's map address was lost to the citation audit (2026-10-16 trial)."""
    text = ('# Vern Chan\n\n## Facts\n'
            f'- {field}: vern.chan@unsw.edu.au\n- Phone: 0400 000 000 [1]\n\n'
            '## Sources\n- [1] gmail:a — 2026-10-16\n')
    kept, unlocated = drop_claims('people/vern-chan.md', text,
                                  [claim.format(field=field), 'Phone: 0400 000 000'])
    assert kept == text.replace('- Phone: 0400 000 000 [1]', '- Phone: Unknown')
    assert unlocated == []


def test_a_glued_heading_and_a_repeated_section_are_merged_not_refused():
    text = ('# Hamish\n\nLead [1].\n\n## Facts\n- Email: h@example.com\n\n## Who they are\n'
            'He leads the program [1]. ## Our relationship\n- Colleagues [1]\n\n'
            '## Uncertainties\n- Unknown\n\n## Uncertainties\n- Whether he stays [1]\n\n'
            '## Sources\n- [1] gmail:a — 2026-10-01\n')
    merged = merge_duplicate_sections('people/hamish.md', text)
    assert 'program [1].\n\n## Our relationship\n- Colleagues [1]' in merged
    assert merged.count('## Uncertainties') == 1 and '- Whether he stays [1]' in merged
    assert not [e for e in validate('people/hamish.md', merged, '', []) if 'occur once' in e or 'Duplicate' in e]


@pytest.mark.parametrize('decisions', ['', '## Key decisions\n- Chose local storage [1]\n\n'])
def test_project_history_is_folded_into_key_decisions(decisions):
    from connectonion.rem.page_review import compact_page
    text = ('# Atlas\n\n' + decisions + '## History\n- 2026-10-01: “Keep it local” [1]\n\n'
            '## Sources\n- [1] codex:s:1 — 2026-10-01\n\nInvestigation: written 2026-10-15\n')
    compact = compact_page('projects/atlas.md', text)
    assert '## History' not in compact and compact.count('## Key decisions') == 1
    assert '- 2026-10-01: “Keep it local” [1]' in compact.split('## Key decisions\n')[1].split('## Sources')[0]
    assert compact.endswith(text.split('## Sources')[1])
    assert not decisions or '- Chose local storage [1]' in compact
    assert compact_page('projects/atlas.md', compact) == compact
    assert compact_page('people/atlas.md', text) == text
    assert compact_page('orgs/atlas.md', text) == text


def test_a_fenced_history_example_is_not_a_project_section():
    from connectonion.rem.page_review import compact_page
    text = '# Atlas\n\n## What it is\n```markdown\n## History\n- Example\n```\n\n## Sources\n- [1] codex:s:1\n'
    assert compact_page('projects/atlas.md', text) == text


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
    # A second title is code's to drop now; a page with none is still refused.
    candidate.write_text(written.replace('# Ody\n', '', 1))
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


def test_a_source_listed_twice_becomes_one_dated_by_its_original():
    from connectonion.rem.page_review import settle_sources
    text = ('# X\n\nA [1]. B [2]. `rows[2]`\n\n## Sources\n- [1] gmail:a — 2026-01-01\n'
            '- [2] gmail:a — 2026-02-02\n- [3] gmail:b — a date the writer typed\n- [4] gmail:c — 2026-04-04\n')
    settled = settle_sources(text, {'gmail:a': '2026-01-05', 'gmail:b': '2026-03-03'})
    assert settled == ('# X\n\nA [1]. B [1]. `rows[2]`\n\n## Sources\n- [1] gmail:a — 2026-01-05\n'
                       '- [3] gmail:b — 2026-03-03\n- [4] gmail:c — 2026-04-04\n')


def test_an_audit_claim_is_found_without_its_citation_and_only_its_sentence_goes():
    """Hamish (2026-10-15 trial): the audit copied the claim without its [7], so no
    line matched and the whole page was refused; the line's other sentence was true."""
    text = ('# H\n\n## History\n- 2026-01-12: Hamish replied that the team would miss him [2]. '
            'Nina later sent a drinks location update [7].\n\n## Sources\n- [2] gmail:a — 2026-01-12\n')
    kept, unlocated = drop_claims('people/h.md', text, ['Nina later sent a drinks location update.'])
    assert unlocated == [] and 'drinks' not in kept
    assert '- 2026-01-12: Hamish replied that the team would miss him [2].' in kept


def _audit_fails_with(monkeypatch, claim):
    finding = {'claim': claim, 'issue': 'x', 'evidence': 'x', 'required_correction': 'remove'}
    monkeypatch.setattr(runner, 'run_claim_task', lambda *_args: {
        'result': json.dumps({'verdict': 'FAIL', 'findings': [finding]}), 'usage': {}})
    monkeypatch.setattr(runner, 'run_task', lambda *args: {'usage': {}})


def test_a_claim_on_a_linked_name_is_found_and_a_claim_already_gone_does_not_refuse(tmp_path, monkeypatch):
    """v193q1 (2026-10-15): 10 of 28 pages were refused because the audit's claim named
    'Sasha Ward' while the page, linked by code, said '[Sasha Ward](...)', or
    because a repair had already rewritten the refuted sentence."""
    kept, unlocated = drop_claims('people/x.md', '# X\n\n## Insight\n- Now: [Sasha Ward](../people/s.md) '
                                  'approved it [1].\n\n## Sources\n- [1] gmail:a — 2026-10-01\n',
                                  ['Sasha Ward approved it.'])
    assert 'approved' not in kept and unlocated == []
    notebook, old, written, items = _person(tmp_path)
    candidate = tmp_path / 'candidate.md'
    candidate.write_text(written.replace('“I can intro you to Sam”', '“Happy to introduce Sam”'))
    _audit_fails_with(monkeypatch, 'A sentence a repair already rewrote.')
    runner.promote_with_repairs(notebook, 'people/ody.md', candidate, old, items, tmp_path, {},
                                workdir=tmp_path, config={}, stage='investigate')
    assert '“send the deck by Friday”' in notebook.read('people/ody.md')
    review = json.loads((tmp_path / 'review.json').read_text())
    assert review['factual_quality'] == 'bounded citation audit failed; 0 refuted claims removed, 1 already gone'


def test_a_page_kept_after_its_audit_failed_says_how_many_claims_went(tmp_path, monkeypatch):
    """b827e4cc: the review record said only "failed" for a page that was saved."""
    notebook, old, written, items = _person(tmp_path)
    candidate = tmp_path / 'candidate.md'
    candidate.write_text(written.replace('“I can intro you to Sam”', '“Happy to introduce Sam”'))
    _audit_fails_with(monkeypatch, 'Ody offered: “Happy to introduce Sam”')
    runner.promote_with_repairs(notebook, 'people/ody.md', candidate, old, items, tmp_path, {},
                                workdir=tmp_path, config={}, stage='investigate')
    assert '“send the deck by Friday”' in notebook.read('people/ody.md')
    review = json.loads((tmp_path / 'review.json').read_text())
    assert review['accepted'] is True
    assert review['factual_quality'] == 'bounded citation audit failed; 1 refuted claims removed'


def test_an_audit_that_could_not_judge_is_recorded_not_a_refusal(tmp_path, monkeypatch):
    """"insufficient" means the audit read too little; nobody showed a claim wrong."""
    notebook, old, written, items = _person(tmp_path)
    written = written.replace('- 2026-10-02 — Ody offered: “I can intro you to Sam” [1] — open',
                              '- 2026-10-02 — Ody offered to introduce Sam [1] — open')
    candidate = tmp_path / 'candidate.md'
    candidate.write_text(written)
    monkeypatch.setattr(runner, 'run_claim_task', lambda *_args: {
        'result': json.dumps({'verdict': 'INSUFFICIENT', 'findings': []}), 'usage': {}})
    monkeypatch.setattr(runner, 'run_task', lambda *args: pytest.fail('nothing to repair'))
    runner.promote_with_repairs(notebook, 'people/ody.md', candidate, old, items, tmp_path, {},
                                workdir=tmp_path, config={}, stage='investigate')
    assert 'introduce Sam' in notebook.read('people/ody.md')
    assert json.loads((tmp_path / 'review.json').read_text())['factual_quality'] == \
        'bounded citation audit insufficient'


def test_a_page_someone_else_changed_meanwhile_gets_no_repair_turn(tmp_path, monkeypatch):
    notebook, old, written, items = _person(tmp_path)
    candidate = tmp_path / 'candidate.md'
    candidate.write_text(written)
    notebook.write('people/ody.md', old + '\nEdited by the user.\n')
    monkeypatch.setattr(runner, 'run_task', lambda *args: pytest.fail('a repair would overwrite their edit'))
    with pytest.raises(runner.RunFailed, match='Page changed during'):
        runner.promote_with_repairs(notebook, 'people/ody.md', candidate, old, items, tmp_path, {},
                                    workdir=tmp_path, config={}, stage='investigate')
    assert 'Edited by the user.' in notebook.read('people/ody.md')


def test_a_person_audit_reads_the_turns_own_mail_and_knows_the_people_rules_and_the_date(tmp_path):
    """A mail the turn was handed but the archive does not hold is still an original;
    who said what, passed events and contact ownership are where person pages went wrong."""
    from connectonion.rem import project_claim_review
    notebook, old, written, items = _person(tmp_path)
    sent = []

    def audit(_workspace, prompt, *_args):
        sent.append(prompt)
        return {'result': json.dumps({'verdict': 'PASS', 'findings': []}), 'usage': {}}

    report, _ = project_claim_review.review(notebook, written, {}, tmp_path, audit, record='people/ody.md',
                                            items=items)
    assert report['verdict'] == 'pass' and report['sources_supplied'] == 1
    assert 'Could you send the deck by Friday?' in sent[0]
    assert 'a cc\'d person is not a party' in sent[0] and 'Today is ' in sent[0]
    project = page('- Built the reader [1]', '- [1] gmail:abc — 2026-10-01\n')
    project_claim_review.review(notebook, project, {}, tmp_path, audit, record='projects/atlas.md', items=items)
    assert 'a cc\'d person is not a party' not in sent[1] and 'Today is ' in sent[1]


def test_a_refuted_arrow_drops_its_diagram_and_keeps_the_page():
    """STR (2026-10-15): the audit refuted a collector -> Postgres arrow copied
    across two diagram lines; no single line held it and the page was refused."""
    text = ('# X\n\n## Overview\nThe flow, as the README tells it [1].\n\n```text\nMelbourne rental collectors\n'
            '  -> Cloud Postgres property_prod\n```\n\n## Paths\n- /a\n\n## Sources\n- [1] codex:a:1 — 2026-10-01\n')
    kept, unlocated = drop_claims('projects/x.md', text, ['Melbourne rental collectors\n  -> Cloud Postgres property_prod'])
    assert unlocated == [] and 'collectors' not in kept and 'The flow, as the README tells it [1].' in kept


def test_a_refuted_unknown_drops_nothing_and_a_sentence_leaves_no_bare_citations():
    """oo-api (2026-10-15): an audited "Unknown" matched every Unknown line, and a
    dropped last sentence left a line of bare citation markers."""
    text = ('# X\n\n## Insight\n- At stake: the owner wanted every model. The gateway is curated. [5][6]\n\n'
            '## Open threads\nUnknown\n\n## Sources\n- [5] codex:a:1 — 2026-10-01\n- [6] codex:a:2 — 2026-10-01\n')
    kept, unlocated = drop_claims('projects/x.md', text, ['Unknown', 'The gateway is curated'])
    assert unlocated == [] and 'Unknown' in kept and '\n[5][6]' not in kept and 'The gateway' not in kept


def test_a_source_cited_in_place_is_numbered_so_its_quote_is_checked(tmp_path):
    """v193q1 STR (2026-10-15): a quote cited as [codex:…] skipped the quote check."""
    from connectonion.rem.page_review import normalize_numbered_sources
    text = ('# X\n\n## Key decisions\n- 2026-08-10 — “start now” [codex:s:9] and [1]\n\n'
            '## Sources\n- [1] codex:s:1 — 2026-08-10\n\nInvestigation: mapped\n')
    fixed = normalize_numbered_sources(text)
    assert '“start now” [2] and [1]' in fixed and '- [2] codex:s:9' in fixed and fixed.endswith('Investigation: mapped\n')
    items = [{'source': 'codex:s:9', 'text': 'please begin', 'role': 'user'},
             {'source': 'codex:s:1', 'text': 'x', 'role': 'user'}]
    assert misquoted(tmp_path, 'projects/x.md', fixed, items)
