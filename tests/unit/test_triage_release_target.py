"""Execute the actual workflow script against mainline and maintenance PR events."""
import json
from pathlib import Path
import shutil
import subprocess

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]


def run_gate(base, target, tracker=None):
    workflow = yaml.load((ROOT / '.github/workflows/triage-metadata.yml').read_text(), Loader=yaml.BaseLoader)
    script = workflow['jobs']['labels-and-release-target']['steps'][0]['with']['script']
    body = f'**Proposed target version:** {target}\n**Estimated release window:** next stable\n'
    if tracker:
        body += '**Forward-port tracking issue (stable patches only):** #200\n'
    context = {'repo': {'owner': 'example', 'repo': 'sdk'}, 'payload': {
        'repository': {'default_branch': 'main'},
        'pull_request': {'number': 1, 'title': 'fix: regression', 'labels': [{'name': 'bug'}],
                         'body': body, 'base': {'ref': base}},
    }}
    node = shutil.which('node')
    assert node, 'Node is required to execute the GitHub Actions JavaScript regression'
    harness = '''
const fs = require('fs');
const input = JSON.parse(fs.readFileSync(0, 'utf8'));
const errors = [], calls = [];
const core = {setFailed: message => errors.push(message), notice: () => {}};
const github = {rest: {issues: {get: async query => {
  calls.push(query.issue_number);
  return {data: input.tracker || {state: 'closed', labels: []}};
}}}};
(async () => {
  await new Function('context', 'github', 'core', 'return (async () => {' + input.script + '})();')(input.context, github, core);
  process.stdout.write(JSON.stringify({errors, calls}));
})().catch(error => { process.stderr.write(String(error)); process.exitCode = 1; });
'''
    result = subprocess.run([node, '-e', harness], input=json.dumps({'script': script, 'context': context, 'tracker': tracker}),
                            text=True, capture_output=True, timeout=15)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


@pytest.mark.parametrize('base,target', [('main', '1.8.4'), ('main', 'next patch'),
                                        ('main', '1.8.4rc1'), ('fix/credential-foundation', '1.8.4')])
def test_mainline_and_stacked_prs_do_not_invent_a_forward_port(base, target):
    assert run_gate(base, target) == {'errors': [], 'calls': []}


@pytest.mark.parametrize('base', ['release/1.7', 'release/1.8'])
def test_maintenance_patch_still_requires_a_tracker(base):
    result = run_gate(base, 'next patch')
    assert len(result['errors']) == 1
    assert 'forward-port' in result['errors'][0]


def test_valid_open_tracker_satisfies_maintenance_gate():
    assert run_gate('release/1.7', '1.7.5', {'state': 'open', 'labels': [{'name': 'forward-port-required'}]}) == {'errors': [], 'calls': [200]}


@pytest.mark.parametrize('tracker', [{'state': 'closed', 'labels': [{'name': 'forward-port-required'}]},
                                    {'state': 'open', 'labels': []}])
def test_closed_or_unlabelled_tracker_still_fails(tracker):
    result = run_gate('release/1.7', '1.7.5', tracker)
    assert len(result['errors']) == 1
    assert result['calls'] == [200]


def test_release_fields_remain_required_on_main():
    result = run_gate('main', 'TBD')
    assert len(result['errors']) == 1
    assert 'Proposed target version' in result['errors'][0]
