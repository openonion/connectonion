"""Allowance reservations and observed harness attempts are different evidence."""
import json
import subprocess
from types import SimpleNamespace

import pytest

from connectonion.rem import runner, service, translate as tr
from connectonion.rem.config import read_config
from connectonion.rem.files import RemError
from test_rem_translate import CHINESE, PAGE, notebook


def boundary(monkeypatch, answer=CHINESE):
    monkeypatch.setattr(runner, 'preflight', lambda: ['co-fixture'])
    calls = []
    def execute(command, **options):
        calls.append(command)
        from pathlib import Path
        workspace = Path(options['cwd'])
        if (workspace / 'page.md').exists():
            (workspace / 'translation.md').write_text(answer)
        return SimpleNamespace(returncode=0, stderr='', stdout=json.dumps({
            'outcome':'natural', 'usage':{'input_tokens':80}}))
    monkeypatch.setattr(runner.subprocess, 'run', execute)
    return calls


@pytest.mark.parametrize('valid', [True, False])
def test_translation_observes_native_attempt_even_when_page_validation_fails(notebook, monkeypatch, valid):
    calls = boundary(monkeypatch, CHINESE if valid else CHINESE.replace('[1]', '[2]'))
    if valid:
        tr.translate(notebook, 'people/avery-lin.md', 'zh')
        tr.translate(notebook, 'people/avery-lin.md', 'zh')
    else:
        with pytest.raises(RemError, match='source ids'):
            tr.translate(notebook, 'people/avery-lin.md', 'zh')
    [log] = service.run_logs(notebook)
    assert len(calls) == 1 and log['runner_attempts'] == 0
    assert log['execution']['attempts'] == log['execution']['completed'] == 1
    assert log['execution']['failed'] == 0
    assert log['usage']['input_tokens'] == 80
    assert log['outcome'] == ('completed' if valid else 'failed')
    assert service.status(notebook)['runner_attempts_today'] == 0
    assert service.status(notebook)['execution_today']['attempts'] == 1


def test_manual_logged_calls_keep_allowance_zero_and_observe_each_attempt(notebook, monkeypatch):
    from connectonion.cli.commands.rem_commands import _logged
    boundary(monkeypatch)
    monkeypatch.setattr('connectonion.rem.quota.read', lambda *a: {})
    def work(update):
        for _ in range(2):
            runner.run_task(notebook, 'fixture', read_config(notebook), 'maintain')
        return {'usage':{'input_tokens':160}, 'changed':[]}
    _logged(notebook, 'people/avery-lin.md', 'investigate', work, quiet=True)
    [log] = service.run_logs(notebook)
    assert log['runner_attempts'] == 0 and log['execution']['attempts'] == 2
    assert service.usage_report(notebook)['execution']['attempts'] == 2


def test_nested_daily_translation_has_one_direct_attempt_without_double_allowance(notebook, monkeypatch):
    from connectonion.rem.daily import _translate_changed
    from connectonion.rem.config import set_config
    boundary(monkeypatch)
    set_config(notebook, ['languages', 'en,zh', 'limits.translations_per_day', '1'])
    _translate_changed(notebook, read_config(notebook), {}, ['people/avery-lin.md'], None, lambda _:None)
    logs = service.run_logs(notebook)
    child = next(r for r in logs if r.get('phase') == 'translate')
    parent = next(r for r in logs if r.get('phase') == 'daily-translation')
    assert child['parent_run_id'] == parent['id']
    assert parent['execution']['attempts'] == 0 and child['execution']['attempts'] == 1
    assert sum(r['runner_attempts'] for r in logs) == 1
    assert service.status(notebook)['runner_attempts_today'] == 1
    assert service.status(notebook)['execution_today']['attempts'] == 1
    assert service.usage_report(notebook)['total']['input_tokens'] == 80


@pytest.mark.parametrize('failure,attempts', [('preflight',0), ('launch',1), ('timeout',1), ('envelope',1)])
def test_execution_boundary_distinguishes_preflight_from_start_attempt(notebook, monkeypatch, failure, attempts):
    from connectonion.rem.execution import capture
    from connectonion.rem.files import state_path, read_json
    boundary(monkeypatch)
    if failure == 'preflight':
        monkeypatch.setattr(runner, 'preflight', lambda: (_ for _ in ()).throw(RemError('fixture config')))
    else:
        def fail(*args, **kw):
            if failure == 'launch':
                raise OSError('fixture unavailable')
            if failure == 'timeout':
                raise subprocess.TimeoutExpired('fixture', 1)
            return SimpleNamespace(returncode=1, stderr='', stdout=json.dumps({
                'outcome':'error', 'usage':{'input_tokens':9}, 'error':'fixture refused'}))
        monkeypatch.setattr(runner.subprocess, 'run', fail)
    record = {'id':'run_fixture', 'runner_attempts':0}
    path = state_path(notebook, 'runs/run_fixture.json')
    with capture(record, path):
        with pytest.raises(RemError):
            runner.run_task(notebook, 'fixture', read_config(notebook), 'extract')
    assert record['execution']['attempts'] == record['execution']['failed'] == attempts
    assert record['execution']['in_flight'] == record['execution']['completed'] == 0
    if attempts:
        assert read_json(path, {})['execution'] == record['execution']


def test_attempt_is_persisted_before_process_returns_and_context_is_restored(notebook, monkeypatch):
    from connectonion.rem.execution import capture
    from connectonion.rem.files import read_json, state_path
    boundary(monkeypatch)
    seen = []
    def process(*args, **kw):
        log = read_json(state_path(notebook, 'runs/run_fixture.json'), {})
        if not seen:
            assert log['execution']['attempts'] == log['execution']['in_flight'] == 1
            assert log['execution']['completed'] == 0
        seen.append(True)
        return SimpleNamespace(returncode=0, stdout='{"outcome":"natural"}', stderr='')
    monkeypatch.setattr(runner.subprocess, 'run', process)
    record = {'id':'run_fixture'}
    with capture(record, state_path(notebook, 'runs/run_fixture.json')):
        runner.run_task(notebook, 'fixture', read_config(notebook), 'maintain')
    assert record['execution']['completed'] == 1
    # A later unobserved invocation must not silently attach to the old run.
    runner.run_task(notebook, 'fixture', read_config(notebook), 'maintain')
    assert record['execution']['attempts'] == 1


@pytest.mark.parametrize('evidence', [None, {}, {'schema':True}, {'attempts':True},
    {'schema':1,'boundary':'direct-co-ai-subprocess','attempts':1,'completed':2,'failed':0,'in_flight':0}])
def test_missing_or_invalid_execution_is_unknown_not_inferred_from_allowance_or_usage(evidence):
    from connectonion.rem.execution import summary
    result = summary([{'execution':evidence,'runner_attempts':8,'usage':{'input_tokens':100}}])
    assert result['attempts'] == result['records_with_evidence'] == 0
    assert result['records_without_evidence'] == 1 and result['provider_model_calls'] is None


def test_execution_summary_preserves_partial_coverage_and_safe_integer_totals():
    from connectonion.rem.execution import summary
    observed = {'schema':1,'boundary':'direct-co-ai-subprocess','attempts':2,
                'completed':1,'failed':1,'in_flight':0}
    large = {**observed, 'attempts':2**53-1,'completed':2**53-1,'failed':0}
    result = summary([{'execution':observed},{'runner_attempts':7},{'execution':large}])
    assert result['attempts'] == 2 and result['records_with_evidence'] == 1
    assert result['records_without_evidence'] == 2 and result['provider_model_calls'] is None


@pytest.mark.parametrize('language', ['en','zh'])
def test_maintenance_separates_daily_allowance_and_recorded_execution(language):
    import re
    from connectonion.rem.reader import TEMPLATE
    from test_rem_reader import _run_reader_js
    source = TEMPLATE.read_text()
    functions = '\n'.join(m.group(0) for name in ['executionLabel','maintenance']
        if (m := re.search(r'function '+name+r'\(.*?\n\}', source, re.S)))
    zh = source[source.index('  zh: {')+len('  zh: '):source.index('\n};\nfunction t(')]
    result = _run_reader_js('UI.zh = '+zh+'; uiLanguage = '+json.dumps(language)+';\n'+functions+r'''
      const REM = {}, scheduleState = () => '', plainLine = String, inline = String, num = String;
      const el = (tag, attrs={}, children=[]) => ({tag,...attrs,children,
        appendChild(x) {this.children.push(x);}});
      console.log(JSON.stringify({body:maintenance({runner_attempts_today:8,
          execution_today:{attempts:1,records_with_evidence:1,records_without_evidence:2}}),
        missing:typeof executionLabel==='function' ? executionLabel(null) : null,
        invalid:typeof executionLabel==='function' ? executionLabel({attempts:true}) : null}));
    ''')
    text = json.dumps(result, ensure_ascii=False)
    assert ('日常调用额度已用' if language=='zh' else 'Daily call allowance used') in text
    assert ('已记录的 AI 进程启动尝试' if language=='zh' else 'AI process attempts recorded') in text
    assert ('模型 API 调用次数未知' if language=='zh' else 'Provider model calls are unknown') in text
    assert ('1，另有未知' if language=='zh' else '1 + unknown') in text
    assert result['missing'] == result['invalid'] == ('未记录' if language=='zh' else 'Not recorded')
    assert 'Model turns today' not in text and '今日模型轮次' not in text


def test_boolean_schema_is_not_execution_evidence():
    from connectonion.rem.execution import summary
    result = summary([{'execution':{'schema':True, 'boundary':'direct-co-ai-subprocess',
        'attempts':1, 'completed':1, 'failed':0, 'in_flight':0}}])
    assert result['records_without_evidence'] == 1 and result['attempts'] == 0


def test_interrupt_records_failed_wrapper_attempt_and_restores_scope(notebook, monkeypatch):
    from connectonion.rem.execution import capture
    from connectonion.rem.files import state_path
    boundary(monkeypatch)
    monkeypatch.setattr(runner.subprocess, 'run', lambda *a, **k: (_ for _ in ()).throw(KeyboardInterrupt()))
    record = {'id':'run_interrupt'}
    with pytest.raises(KeyboardInterrupt), capture(record, state_path(notebook, 'runs/run_interrupt.json')):
        runner.run_task(notebook, 'fixture', read_config(notebook), 'maintain')
    assert record['execution']['failed'] == 1 and record['execution']['in_flight'] == 0
    other = {'id':'run_other'}
    with capture(other, state_path(notebook, 'runs/run_other.json')):
        assert 'parent_run_id' not in other


def test_running_translation_uses_existing_process_liveness_marker(notebook, monkeypatch):
    import os
    boundary(monkeypatch)
    def process(command, **options):
        [log] = service.run_logs(notebook)
        assert log['pid'] == os.getpid() and log['host']
        assert service.seen_outcome(log) == 'running' and log['execution']['in_flight'] == 1
        from pathlib import Path
        (Path(options['cwd'])/'translation.md').write_text(CHINESE)
        return SimpleNamespace(returncode=0, stderr='', stdout='{"outcome":"natural"}')
    monkeypatch.setattr(runner.subprocess, 'run', process)
    tr.translate(notebook, 'people/avery-lin.md', 'zh')


def test_receipt_write_failure_after_harness_return_does_not_claim_start_failure(notebook, monkeypatch):
    from connectonion.rem import execution
    from connectonion.rem.files import state_path
    calls = boundary(monkeypatch)
    actual_write, writes = execution.write_json, []
    def fail_receipt(path, record):
        writes.append(True)
        if len(writes) == 2:
            raise OSError('fixture receipt write unavailable')
        return actual_write(path, record)
    monkeypatch.setattr(execution, 'write_json', fail_receipt)
    record = {'id':'run_storage'}
    with pytest.raises(OSError, match='receipt write'), execution.capture(
            record, state_path(notebook, 'runs/run_storage.json')):
        runner.run_task(notebook, 'fixture', read_config(notebook), 'maintain')
    assert len(calls) == 1 and record['execution']['completed'] == 1
