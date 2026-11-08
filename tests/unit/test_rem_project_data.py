"""Fictional notebook contracts for the project views; no network or owner data."""
from datetime import date
import json

import pytest

from connectonion.rem.project_data import enrich_records

TODAY = date(2026, 11, 8)


def page(path='projects/harbour.md', title='Harbour', facts='', opened='', standing='', sources=''):
    return {'path': path, 'category': path.split('/')[0], 'title': title,
            'text': f'# {title}\n\n## Facts\n{facts}\n\n## Open threads\n{opened}\n\n## Where it stands\n{standing}\n\n## Sources\n{sources}\n',
            'updated': '2099-01-01', 'written': True}


def enrich(tmp_path, rows, contexts=None, **kwargs):
    enrich_records(tmp_path, rows, contexts or {}, today=TODAY, **kwargs)
    return rows[0]


@pytest.mark.parametrize('category', ['projects', 'people', 'orgs'])
def test_directions_and_agent_requests_are_not_human_debts(tmp_path, category):
    row = page(f'{category}/harbour.md', opened='\n'.join([
        '- You owe [Fern](../people/fern.md) a report. [1]',
        '- You asked [Fern](../people/fern.md) to send the contract. [2]',
        '- The user asked: "Build a preview". [3]',
        '- The user asked Codex to email Fern a report. [3]',
    ]), sources='- [1] gmail:in\n- [2] gmail:out\n- [3] codex:session:12')
    result = enrich(tmp_path, [row, page('people/fern.md', 'Fern')])
    assert [item['kind'] for item in result['open']] == ['owed', 'waiting', 'agent', 'agent']
    assert result['kind_counts'] == {'owed': 1, 'waiting': 1, 'agent': 2, 'answerable': 0}
    assert result['open'][0]['who'] == 'people/fern.md'
    assert result['open'][0]['sources'][0]['source'] == 'gmail:in'


def test_answerable_requires_an_actual_answer_not_a_repeated_user_question(tmp_path):
    row = page(opened='- The user asked: "How many cedar invoices were processed?" [1]',
               standing='- Answer: 37 cedar invoices were processed. [2]',
               sources='- [1] codex:session:1\n- [2] codex:session:2')
    result = enrich(tmp_path, [row])
    assert result['open'][0]['kind'] == 'answerable'
    assert result['open'][0]['answer']['source'] == 'codex:session:2'
    row['text'] = row['text'].replace('Answer: 37 cedar invoices were processed.', 'The user asked how many cedar invoices were processed.')
    assert enrich(tmp_path, [row])['open'][0]['kind'] == 'agent'


def test_agent_can_be_answered_by_retained_assistant_but_not_input_only(tmp_path):
    row = page(opened='- The user asked: "How many cedar invoices were processed?" [1]', sources='- [1] codex:s:1\n- [2] codex:s:2')
    context = {'codex:s:2': {'excerpt': '37 cedar invoices were processed.', 'source': 'codex', 'role': 'assistant'}}
    assert enrich(tmp_path, [row], context)['open'][0]['kind'] == 'answerable'
    context['codex:s:2']['input_scope'] = 'Your input only.'
    assert enrich(tmp_path, [row], context)['open'][0]['kind'] == 'agent'


def test_top_three_debts_weight_waiter_and_explain_score(tmp_path):
    client = page('people/fern.md', 'Fern', facts='- Role: paying client [1]')
    opened = '\n'.join(f'- You owe [Fern](../people/fern.md) report {i}, since 2026-10-01. [1]' for i in range(8))
    row = page(opened=opened, sources='- [1] gmail:debt')
    result = enrich(tmp_path, [row, client])
    assert result['score'] == 22.5  # 3 * (5 * 1.5), no activity invented from mtime
    assert result['priority'] == 1
    assert len(result['reasons']) == 3
    assert all(reason['source'] == 'gmail:debt' for reason in result['reasons'])
    assert result['last_activity'] is None


def test_dates_are_explicit_and_mail_deadline_is_sourced(tmp_path):
    row = page(facts='- Started: 2026-04-03 [1]\n- Last activity: Unknown',
               opened='- You owe Fern the report requested on 2026-11-01. [1]',
               sources='- [1] gmail:request')
    contexts = {'gmail:request': {'excerpt': 'Please deliver the report by the 2026-11-12.', 'time': '2026-11-01T12:00:00Z'}}
    result = enrich(tmp_path, [row], contexts)
    assert result['started'] == '2026-04-03'
    assert result['last_activity'] == '2026-11-01'
    assert result['promised'][0]['date'] == '2026-11-12'
    assert result['promised'][0]['source'] == 'gmail:request'
    assert result['open'][0]['due'] == '2026-11-12'
    assert result['health'] == 'at_risk'


def test_invalid_dates_and_yearless_promises_never_become_calendar_dates(tmp_path):
    row = page(opened='- You owe a report by 2026-02-30 and a demo by November 20. [1]', sources='- [1] gmail:one')
    result = enrich(tmp_path, [row])
    assert result['started'] is None and result['last_activity'] is None
    assert all(p['date'] is None for p in result['promised'])
    assert result['priority'] == 4


def test_overdue_and_quiet_health_with_sources(tmp_path):
    overdue = page(opened='- You owe Fern a delivery by 2026-10-01. [1]', sources='- [1] gmail:one')
    assert enrich(tmp_path, [overdue])['health'] == 'off_track'
    assert overdue['health_reason']['source'] == 'gmail:one'
    quiet = page(facts='- Last activity: 2026-08-01 [1]', sources='- [1] codex:s:1')
    assert enrich(tmp_path, [quiet])['health'] == 'quiet'
    assert quiet['score'] == 0 and quiet['priority'] == 0


def test_manual_snooze_wins_over_pin_then_expires_without_writes(tmp_path):
    state = tmp_path / '.state'
    state.mkdir()
    override = state / 'project-overrides.json'
    override.write_text(json.dumps({'projects/harbour.md': {'pin': True, 'snooze_until': '2026-11-10', 'at': '2026-11-08'}}))
    row = page(opened='- You owe Fern a report. [1]')
    before = override.read_bytes()
    assert enrich(tmp_path, [row], local=True)['priority'] == 0
    assert row['reasons'][0]['source'] == '.state/project-overrides.json#projects/harbour.md'
    assert 'snooz' in row['reasons'][0]['text'].lower()
    enrich_records(tmp_path, [row], {}, today=date(2026, 11, 10), local=True)
    assert row['priority'] == 1 and row['pinned'] is True
    assert override.read_bytes() == before
    assert enrich(tmp_path, [row], local=False)['priority'] == 4
    assert row['pinned'] is False


def test_duplicates_and_parent_are_suggestions_not_merges(tmp_path):
    parent = page(title='Cedar', facts='- Repository: https://github.com/cedar-labs/cedar [1]')
    duplicate = page('projects/cedar-copy.md', 'CEDAR')
    child = page('projects/api.md', 'oo-api', facts='- Repository: https://github.com/cedar-labs/oo-api [1]',
                 standing='- Part of [Cedar](harbour.md). [1]')
    rows = [parent, duplicate, child]
    original = [r['text'] for r in rows]
    enrich(tmp_path, rows)
    assert duplicate['same_as'][0]['path'] == parent['path']
    assert child['parent']['path'] == parent['path']
    assert child['parent']['suggestion'] is True
    assert [r['text'] for r in rows] == original and len(rows) == 3


def test_recent_issues_only_count_once_and_are_capped(tmp_path):
    row = page(facts='- Repository: https://github.com/cedar-labs/harbour [1]')
    issues = [{'url': f'https://github.com/cedar-labs/harbour/issues/{i}', 'state': 'OPEN',
               'labels': [{'name': 'bug'}, {'name': 'priority:high'}], 'updatedAt': '2026-11-07T00:00:00Z'} for i in range(6)]
    issues += [{'url': 'https://github.com/cedar-labs/harbour/issues/99', 'state': 'OPEN',
                'labels': [], 'updatedAt': '2026-09-01T00:00:00Z'}]
    result = enrich(tmp_path, [row], issues={'cedar-labs/harbour': issues})
    assert result['score'] == 4
    assert result['priority'] == 4
    assert result['reasons'][0]['source'].startswith('https://github.com/')


def test_snapshot_keeps_existing_fields_and_enriches_projects(tmp_path):
    from connectonion.rem.reader import snapshot
    (tmp_path / 'projects').mkdir()
    row = page(opened='- The user asked Codex to build a preview. [1]', sources='- [1] codex:s:1')
    (tmp_path / row['path']).write_text(row['text'])
    result = next(r for r in snapshot(tmp_path)['records'] if r['category'] == 'projects')
    assert result['text'] == row['text'] and result['title'] == 'Harbour'
    assert result['kind_counts']['agent'] == 1
    assert set(('priority', 'score', 'reasons', 'health', 'health_reason', 'parent', 'same_as', 'promised', 'started', 'last_activity')) <= result.keys()


def test_plain_named_person_beats_session_source_and_internal_user_requests(tmp_path):
    row = page(opened='- The user asked Fern to send the contract. [1]\n- Fern asked you to send the invoice. [1]', sources='- [1] codex:s:1')
    result = enrich(tmp_path, [row, page('people/fern.md', 'Fern')])
    assert [item['kind'] for item in result['open']] == ['waiting', 'owed']
    assert all(item['who'] == 'people/fern.md' for item in result['open'])


def test_declined_answer_and_user_only_summary_are_not_answerable(tmp_path):
    row = page(opened='- The user asked: "How many cedar invoices were processed last night?" [1]',
               standing='- Answer: 37 cedar invoices were processed. [2]',
               sources='- [1] codex:s:1\n- [2] codex:s:2')
    contexts = {'codex:s:2': {'excerpt': '37 cedar invoices were processed.', 'input_scope': 'Your input only.', 'time': '2026-09-01'}}
    assert enrich(tmp_path, [row], contexts)['open'][0]['kind'] == 'agent'


def test_recent_bug_and_milestone_change_health_and_have_real_sources(tmp_path):
    row = page(facts='- Repository: cedar-labs/harbour')
    issue = {'url': 'https://github.com/cedar-labs/harbour/issues/1', 'state': 'OPEN',
             'labels': ['bug'], 'updatedAt': '2026-11-07', 'milestone': {'dueOn': '2026-11-10'}}
    result = enrich(tmp_path, [row], issues={'cedar-labs/harbour': [issue]})
    assert result['health'] == 'at_risk'
    assert result['health_reason']['source'] == issue['url']
    assert result['score'] == 5


def test_existing_github_context_can_supply_priority_without_new_state(tmp_path):
    row = page(facts='- Repository: cedar-labs/harbour', sources='- [1] github:cedar-labs/harbour#1')
    contexts = {'github:cedar-labs/harbour#1': {'excerpt': 'State: OPEN\nUpdated: 2026-11-06\nLabels: bug, priority:high\nTitle: Repair preview', 'source': 'github'}}
    result = enrich(tmp_path, [row], contexts)
    assert result['score'] == 1
    assert result['reasons'][0]['source'] == 'github:cedar-labs/harbour#1'


def test_direction_dates_and_health_ignore_closed_obligations(tmp_path):
    from connectonion.rem.threads import done_key
    row = page(opened='- You owe Fern a report by 2026-10-01. [1]')
    key = done_key(row['path'], 'You owe Fern a report by 2026-10-01. [1]')
    result = enrich(tmp_path, [row], local=True, states={key: {'state': 'done'}})
    assert result['open'] == [] and result['promised'] == []
    assert result['health'] == 'quiet' and result['score'] == 0


def test_parent_suggestion_cites_the_relationship_line_and_avoids_cycles(tmp_path):
    parent = page(title='Cedar')
    child = page('projects/child.md', 'Cedar API', standing='- Part of [Cedar](harbour.md). [2]\n- Nothing else. [3]', sources='- [2] github:cedar-labs/api#4\n- [3] codex:s:1')
    enrich(tmp_path, [parent, child])
    assert child['parent']['source'] == 'github:cedar-labs/api#4'
    parent['text'] += '\n## Context\n- Part of [Cedar API](child.md). [1]\n'
    enrich(tmp_path, [parent, child])
    assert parent['parent'] is None and child['parent'] is None


def test_closed_invoice_does_not_keep_money_pressure(tmp_path):
    from connectonion.rem.threads import done_key
    text = 'You owe Fern an unpaid invoice for AUD 12000. [1]'
    row = page(opened='- ' + text)
    result = enrich(tmp_path, [row], local=True, states={done_key(row['path'], text): {'state': 'done'}})
    assert result['score'] == 0


def test_mail_deadline_does_not_use_unrelated_or_quoted_promises(tmp_path):
    row = page(opened='- You owe Fern the cedar report. [1]', sources='- [1] gmail:request')
    contexts = {'gmail:request': {'excerpt': 'Please deliver the cedar report by 2026-11-12.\nThe pine demo is due 2026-11-01.\n> Please deliver the cedar report by 2026-10-01.'}}
    result = enrich(tmp_path, [row], contexts)
    assert [p['date'] for p in result['promised']] == ['2026-11-12']


def test_deadline_health_cites_the_mail_that_contains_the_due_date(tmp_path):
    row = page(opened='- You owe Fern the cedar report. [1][2]', sources='- [1] codex:s:1\n- [2] gmail:request')
    result = enrich(tmp_path, [row], {'gmail:request': {'excerpt': 'Please deliver the cedar report by 2026-11-01.'}})
    assert result['health_reason']['source'] == 'gmail:request'


def test_named_org_in_agent_request_is_not_a_human_addressee(tmp_path):
    row = page(opened='- The user proposed publishing a video on Cedar Labs official page and asked for a preview. [1]', sources='- [1] codex:s:1')
    result = enrich(tmp_path, [row, page('orgs/cedar.md', 'Cedar Labs')])
    assert result['open'][0]['kind'] == 'agent'
    assert result['open'][0]['who'] is None


def test_recorded_unresolved_blocker_is_at_risk_even_without_recent_activity(tmp_path):
    row = page()
    row['text'] += '\n## Latest issues\n- Deployment is blocked by unavailable signing; no recovery reported. [4]\n'
    result = enrich(tmp_path, [row])
    assert result['health'] == 'at_risk'
    assert result['health_reason']['cite'] == '4'


def test_answer_must_match_task_and_explicit_date_scope(tmp_path):
    row = page(opened='- The user asked: "How many cedar invoices were queued?" [1]',
               standing='- Answer: 37 cedar invoices were processed. [2]', sources='- [1] codex:s:1\n- [2] codex:s:2')
    assert enrich(tmp_path, [row])['open'][0]['kind'] == 'agent'
    row['text'] = row['text'].replace('queued?', 'processed on 2026-11-07?').replace('37 cedar invoices were processed.', '37 cedar invoices were processed on 2026-10-01.')
    assert enrich(tmp_path, [row])['open'][0]['kind'] == 'agent'


def test_issue_reader_paginates_and_returns_metadata_without_writing(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from connectonion.rem.project_issues import fetch_project_issues
    calls = []
    def run(argv, **kwargs):
        calls.append(argv)
        row = {'url': f'https://github.com/cedar-labs/harbour/issues/{len(calls)}',
               'state': 'OPEN', 'updatedAt': '2026-11-07', 'labels': {'nodes': [{'name': 'bug'}]}, 'milestone': None}
        return SimpleNamespace(stdout=json.dumps({'data': {'repository': {'issues': {
            'nodes': [row], 'pageInfo': {'hasNextPage': len(calls) == 1, 'endCursor': 'next'}}}}}))
    monkeypatch.setattr('connectonion.rem.project_issues.subprocess.run', run)
    rows = fetch_project_issues([page(facts='- Repository: cedar-labs/harbour')])
    assert len(rows['cedar-labs/harbour']) == 2
    assert 'cursor=next' in calls[1]
    assert rows['cedar-labs/harbour'][0]['labels'] == [{'name': 'bug'}]
    assert not list(tmp_path.iterdir())


def test_issue_reader_fails_loudly_instead_of_claiming_zero_issues(monkeypatch):
    import subprocess
    from connectonion.rem.project_issues import fetch_project_issues
    def fail(*args, **kwargs):
        raise subprocess.CalledProcessError(1, 'gh', stderr='not authenticated')
    monkeypatch.setattr('connectonion.rem.project_issues.subprocess.run', fail)
    with pytest.raises(subprocess.CalledProcessError):
        fetch_project_issues([page(facts='- Repository: cedar-labs/harbour')])


def test_grouped_source_labels_keep_individual_source_ids(tmp_path):
    row = page(opened='- The user asked Codex to build a preview. [1]', sources='- [1] codex:s:1; codex:s:2 — 2026-11-01')
    result = enrich(tmp_path, [row], {'codex:s:2': {'time': '2026-11-01'}})
    assert [s['source'] for s in result['open'][0]['sources']] == ['codex:s:1', 'codex:s:2']
    assert result['open'][0]['since'] == '2026-11-01'


def test_component_with_same_repo_owner_and_named_product_gets_parent_hint(tmp_path):
    parent = page(title='Cedar', facts='- Repository: https://github.com/cedar-labs/cedar')
    child = page('projects/api.md', 'oo-api', facts='- Repository: https://github.com/cedar-labs/oo-api', standing='- Backend for Cedar. [2]')
    enrich(tmp_path, [parent, child])
    assert child['parent']['path'] == parent['path']
    assert child['parent']['cite'] == '2'


def test_date_digits_and_negation_are_not_an_answer_to_a_quantity_question(tmp_path):
    row = page(opened='- The user asked: "How many cedar invoices were processed?" [1]',
               standing='- 2026-10-01: cedar invoices were not processed. [2]', sources='- [1] codex:s:1\n- [2] codex:s:2')
    assert enrich(tmp_path, [row])['open'][0]['kind'] == 'agent'


def test_mail_task_matching_excludes_pronouns_and_common_request_words(tmp_path):
    row = page(opened='- You owe Fern the report. [1]', sources='- [1] gmail:one')
    contexts = {'gmail:one': {'excerpt': 'You need to return the contract by 2026-11-10. Please send the report by 2026-11-20.'}}
    result = enrich(tmp_path, [row], contexts)
    assert [p['date'] for p in result['promised']] == ['2026-11-20']


def test_explicit_project_activity_wins_over_mapped_or_context_dates(tmp_path):
    row = page(facts='- Last activity: 2026-08-01 [1]', sources='- [1] codex:s:1')
    row['text'] += '\n## Paths\n- Last seen: 2026-11-07\n'
    result = enrich(tmp_path, [row], {'codex:s:1': {'time': '2026-11-06'}})
    assert result['last_activity'] == '2026-08-01'
    assert result['date_sources']['last_activity']['source'] == 'codex:s:1'


def test_mapped_last_seen_is_real_activity_but_investigation_is_not(tmp_path):
    row = page()
    row['text'] += '\n## Paths\n- Last seen: 2026-08-02\n\nInvestigation: written 2026-11-07\n'
    result = enrich(tmp_path, [row])
    assert result['last_activity'] == '2026-08-02'
    assert result['date_sources']['last_activity']['source'] == row['path'] + '#paths'
