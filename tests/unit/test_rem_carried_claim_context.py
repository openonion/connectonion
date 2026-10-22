"""Changed claims must not inherit the old-page exemption by substring."""

import json

import pytest

from connectonion.rem import project_claim_review
from connectonion.rem.files import Notebook


SOURCES = '\n\n## Sources\n- [1] gmail:first\n- [2] gmail:second\n'


def audit(tmp_path, before, after, claim):
    finding = {'claim': claim, 'issue': 'Not supported by its cited original',
               'evidence': 'Synthetic negative control', 'required_correction': 'Remove'}

    def verdict(*_args):
        return {'result': json.dumps({'verdict': 'FAIL', 'findings': [finding]})}

    report, _ = project_claim_review.review(Notebook(tmp_path), '# Atlas\n\n' + after + SOURCES,
        {}, tmp_path, verdict, carried='# Atlas\n\n' + before + SOURCES,
        items=[{'source': 'gmail:first', 'text': 'A source, not evidence for the synthetic claim.'},
               {'source': 'gmail:second', 'text': 'A different original.'}])
    return report, finding


@pytest.mark.parametrize('before,after,claim', [
    ('Avery is nowhere to be found. [1]', 'Avery is now here to be found. [1]',
     'Avery is now here to be found.'),
    ('Avery is unable to pay.', 'able to pay.', 'able to pay.'),
    ('Avery approved the launch only if the safety check passes. [1]',
     'Avery approved the launch [1]', 'Avery approved the launch'),
    ('Avery approved the launch. Only if the safety check passes. [1]',
     'Avery approved the launch. [1]', 'Avery approved the launch.'),
    ('Avery approved the launch. [1]', 'Avery approved the launch. [2]',
     'Avery approved the launch.'),
    ('## History\nAvery approved the launch. [1]',
     '## Open threads\nAvery approved the launch. [1]', 'Avery approved the launch.'),
    ('```text\nAvery approved the launch.\n```',
     'Avery approved the launch. [1]', 'Avery approved the launch.'),
    ('## Avery approved the launch.\nUnknown',
     'Avery approved the launch. [1]', 'Avery approved the launch.'),
    ('Avery approved the launch. [1]',
     'Avery approved the launch. [1]\n\n## Now\nAvery approved the launch. [2]',
     'Avery approved the launch.'),
])
def test_changed_claims_remain_active_failures(tmp_path, before, after, claim):
    report, finding = audit(tmp_path, before, after, claim)
    assert report['verdict'] == 'fail'
    assert report['findings'] == [finding]
    assert report['carried_findings'] == []


@pytest.mark.parametrize('before,after,claim', [
    ('## Insight\nAvery leads\n the lab. [1]',
     '## Insight\nAvery leads the lab. [1]', 'Avery leads the lab.'),
    ('## Insight\nAvery leads the lab. [1]',
     '## Insight\nAvery leads the lab. [1]\n\nA new unrelated paragraph. [2]',
     'Avery leads the lab.'),
    ('## Insight\nAvery leads the lab. [1] A second sentence stays. [2]',
     '## Insight\nAvery leads the lab. [1] A second sentence stays. [2]',
     'Avery leads the lab.'),
])
def test_unchanged_full_contexts_still_protect_carried_content(tmp_path, before, after, claim):
    report, finding = audit(tmp_path, before, after, claim)
    assert report['verdict'] == 'insufficient' and report['findings'] == []
    assert report['carried_findings'] == [finding]


def test_citation_renumbering_keeps_the_original_identity(tmp_path):
    before = '# Atlas\n\n## Insight\nAvery leads the lab. [7]\n\n## Sources\n- [7] gmail:first\n'
    candidate = '# Atlas\n\n## Insight\nAvery leads the lab. [1]' + SOURCES
    finding = {'claim': 'Avery leads the lab.', 'issue': 'Unsupported',
               'evidence': '', 'required_correction': 'Remove'}
    report, _ = project_claim_review.review(Notebook(tmp_path), candidate, {}, tmp_path,
        lambda *_args: {'result': json.dumps({'verdict': 'FAIL', 'findings': [finding]})},
        carried=before, items=[{'source': 'gmail:first', 'text': 'Hello'}])
    assert report['verdict'] == 'insufficient' and report['carried_findings'] == [finding]


@pytest.mark.parametrize('before,after', [
    ('Avery approved the launch. [9]', 'Avery approved the launch. [9]'),
    ('Avery approved the launch. [1] Rowan rejected it. [2]',
     'Avery approved the launch. [2] Rowan rejected it. [1]'),
    ('## History\n### Scope\nAvery approved the launch. [1]',
     '## Now\n### Scope\nAvery approved the launch. [1]'),
])
def test_unknown_or_moved_source_context_cannot_supply_an_exemption(tmp_path, before, after):
    report, finding = audit(tmp_path, before, after, 'Avery approved the launch.')
    assert report['verdict'] == 'fail' and report['findings'] == [finding]
    assert report['carried_findings'] == []


def test_unchanged_context_can_remain_before_a_new_sentence(tmp_path):
    report, finding = audit(tmp_path, 'Avery leads the lab. [1]',
        'Avery leads the lab. [1] Rowan asked for a review. [2]', 'Avery leads the lab.')
    assert report['verdict'] == 'insufficient' and report['carried_findings'] == [finding]


@pytest.mark.parametrize('verdict', ['FAIL', 'PASS', 'INSUFFICIENT'])
def test_changed_condition_cannot_promote_a_candidate_after_a_failed_audit(tmp_path, monkeypatch, verdict):
    from connectonion.rem import runner
    from connectonion.rem.config import prepare

    prepare(tmp_path)
    notebook, record = Notebook(tmp_path), 'projects/atlas.md'
    notebook.stub_project(record, 'Atlas')
    original = (notebook.read(record).replace('- Unknown — not investigated yet', '- Unknown')
                .replace('## What it is\n- Unknown',
                         '## What it is\nLaunch is approved only after safety checks. [1]')
                .replace('- (none yet)', '- [1] codex:synthetic — 2026-10-01'))
    path = tmp_path / 'candidate.md'
    path.write_text(original)
    items = [{'source': 'codex:synthetic', 'text': 'Approval is conditional on safety checks.'}]
    runner._promote_candidate(notebook, record, path, notebook.read(record), items, tmp_path, None)
    original = notebook.read(record)
    path.write_text(original.replace('Launch is approved only after safety checks.', 'Launch is approved'))
    finding = {'claim': 'Launch is approved', 'issue': 'The condition was removed',
               'evidence': 'Approval is conditional on safety checks.',
               'required_correction': 'Restore the safety condition'}
    monkeypatch.setattr(runner, 'run_claim_task', lambda *_args: {
        'result': json.dumps({'verdict': verdict, 'findings': [finding]})})
    with pytest.raises(runner.RunFailed, match='claim audit did not pass'):
        runner._promote_candidate(notebook, record, path, original, items, tmp_path, None,
                                  claim_config={}, carried=original)
    assert notebook.read(record) == original
    report = json.loads((tmp_path / 'claim-review.json').read_text())
    assert report['findings'] == [finding] and report['carried_findings'] == []
    assert json.loads((tmp_path / 'review.json').read_text())['accepted'] is False


def test_moving_the_same_ordered_citations_between_sentences_is_not_carried(tmp_path):
    report, finding = audit(tmp_path,
        'Avery approved the launch. [1] Blair declined. [2]',
        'Avery approved the launch. Blair declined. [1][2]', 'Avery approved the launch.')
    assert report['verdict'] == 'fail' and report['findings'] == [finding]
    assert report['carried_findings'] == []


def test_changed_page_subject_does_not_exempt_a_pronoun_claim(tmp_path):
    finding = {'claim': 'She approved the launch.', 'issue': 'Wrong subject',
               'evidence': 'The original names Avery.', 'required_correction': 'Restore attribution'}
    report, _ = project_claim_review.review(Notebook(tmp_path),
        '# Blair\n\nShe approved the launch. [1]' + SOURCES, {}, tmp_path,
        lambda *_args: {'result': json.dumps({'verdict': 'FAIL', 'findings': [finding]})},
        carried='# Avery\n\nShe approved the launch. [1]' + SOURCES,
        items=[{'source': 'gmail:first', 'text': 'Avery approved the launch.'}])
    assert report['verdict'] == 'fail' and report['findings'] == [finding]
    assert report['carried_findings'] == []


@pytest.mark.parametrize('qualifier', ['Only if the safety check passes. [2]', '- Only if the safety check passes. [2]'])
def test_removing_an_adjacent_old_qualification_requires_review(tmp_path, qualifier):
    report, finding = audit(tmp_path,
        'Avery approved the launch. [1]\n\n' + qualifier,
        'Avery approved the launch. [1]', 'Avery approved the launch.')
    assert report['verdict'] == 'fail' and report['findings'] == [finding]
    assert report['carried_findings'] == []


@pytest.mark.parametrize('verdict', ['FAIL', 'PASS'])
def test_deferred_old_findings_are_saved_as_unverified_not_a_factual_pass(tmp_path, monkeypatch, verdict):
    from connectonion.rem import runner
    from connectonion.rem.config import prepare

    prepare(tmp_path)
    notebook, record = Notebook(tmp_path), 'projects/atlas.md'
    notebook.stub_project(record, 'Atlas')
    original = (notebook.read(record).replace('- Unknown — not investigated yet', '- Unknown')
                .replace('## What it is\n- Unknown', '## What it is\nAn existing description. [1]')
                .replace('- (none yet)', '- [1] codex:synthetic — 2026-10-01'))
    path = tmp_path / 'candidate.md'
    path.write_text(original)
    items = [{'source': 'codex:synthetic', 'text': 'The turn has only partial material.'}]
    runner._promote_candidate(notebook, record, path, notebook.read(record), items, tmp_path, None)
    original = notebook.read(record)
    path.write_text(original)
    finding = {'claim': 'An existing description.', 'issue': 'Not established in this packet',
               'evidence': '', 'required_correction': 'Remove'}
    monkeypatch.setattr(runner, 'run_claim_task', lambda *_args: {
        'result': json.dumps({'verdict': verdict, 'findings': [finding]})})
    runner._promote_candidate(notebook, record, path, original, items, tmp_path, None,
                              claim_config={}, carried=original)
    report = json.loads((tmp_path / 'claim-review.json').read_text())
    assert report['verdict'] == 'insufficient' and report['carried_findings'] == [finding]
    saved = json.loads((tmp_path / 'review.json').read_text())
    assert saved['accepted'] is True
    assert saved['factual_quality'] == 'bounded citation audit insufficient; 1 unchanged findings deferred'
    assert notebook.read(record) == original
