import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from connectonion.network.host.control_center.bundle import Bundle
from connectonion.network.host.control_center.reviewer import SkillReviewer, review_payload
from connectonion.network.host.control_center.runtime import RuntimeErrorState


def test_entire_executable_source_is_supplied_and_bounded():
    bundle = Bundle({'index.html': b'<h1>Hello</h1>', 'chunk.js': b'console.log(1)',
                     'module.wasm': b'\x00asm\x01\x00\x00\x00'})
    payload = review_payload(bundle)
    assert payload['files']['chunk.js']['text'] == 'console.log(1)'
    assert payload['files']['module.wasm']['base64']
    with pytest.raises(RuntimeErrorState, match='budget'):
        review_payload(bundle, max_bytes=1)


def test_reviewer_invokes_fresh_worker_with_pinned_policy_and_exact_revision(monkeypatch):
    import subprocess
    calls = []
    bundle = Bundle({'index.html': b'<h1>Hello</h1>'})
    def run(command, **kwargs):
        calls.append((command, kwargs))
        request = json.loads(kwargs['input'])
        assert request['bundle']['revision'] == bundle.revision
        assert 'control-center-review' in request['policy']
        return SimpleNamespace(returncode=0, stdout=json.dumps({
            'result': {'schema': 1, 'revision': bundle.revision, 'status': 'approved', 'findings': []},
            'cost_usd': 0.001}), stderr='')
    monkeypatch.setattr(subprocess, 'run', run)
    reviewer = SkillReviewer()
    first, second = reviewer(bundle), reviewer(bundle)
    assert first.execution_id != second.execution_id
    assert first.model == reviewer.model
    assert calls[0][1]['timeout'] == reviewer.timeout
    assert calls[0][1]['cwd'] != calls[1][1]['cwd']


@pytest.mark.parametrize('bad', ['revision', 'schema', 'extra', 'cost', 'blocker'])
def test_model_cannot_write_runtime_provenance_or_approve_another_revision(monkeypatch, bad):
    import subprocess
    bundle = Bundle({'index.html': b'<h1>Hello</h1>'})
    result = {'schema': 1, 'revision': bundle.revision, 'status': 'approved', 'findings': []}
    envelope = {'result': result, 'cost_usd': 0.01}
    if bad == 'revision': result['revision'] = 'sha256:' + '0' * 64
    if bad == 'schema': result['schema'] = 2
    if bad == 'extra': result['review_id'] = 'author-supplied'
    if bad == 'cost': envelope['cost_usd'] = 99
    if bad == 'blocker': result['findings'] = [{'severity': 'blocker', 'message': 'unsafe', 'path': 'index.html'}]
    monkeypatch.setattr(subprocess, 'run', lambda *a, **kw: SimpleNamespace(
        returncode=0, stdout=json.dumps(envelope), stderr=''))
    with pytest.raises(RuntimeErrorState):
        SkillReviewer()(bundle)
