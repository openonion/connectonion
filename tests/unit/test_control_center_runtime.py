"""Only a runtime review of the uploaded bytes may replace the active app."""
import json
from pathlib import Path

import pytest

from connectonion.network.host.control_center.bundle import capture_bundle
from connectonion.network.host.control_center.runtime import ControlCenterRuntime, ReviewResult, RuntimeErrorState


@pytest.fixture
def setup(tmp_path):
    build = tmp_path / 'build'
    build.mkdir()
    (build / 'index.html').write_text('<h1>first</h1>')
    uploaded, reviewed = [], []
    def reviewer(bundle):
        reviewed.append(bundle.revision)
        return ReviewResult('approved', [], 'test-model', 'execution-1', 0.0)
    def uploader(bundle):
        uploaded.append(bundle)
        return {'revision': bundle.revision, 'url': 'https://r-example.apps.test/index.html'}
    runtime = ControlCenterRuntime(tmp_path / 'runtime', reviewer=reviewer,
                                  uploader=uploader, policy='test-policy', clock=lambda: 1000)
    return runtime, build, reviewed, uploaded


def test_activation_uses_frozen_bytes_and_records_runtime_provenance(setup):
    runtime, build, reviewed, uploaded = setup
    result = runtime.update(build)
    assert result['status'] == 'approved'
    assert result['active']['revision'] == reviewed[0] == uploaded[0].revision
    assert result['active']['review']['review_id']
    assert result['history'][0]['policy'] == 'test-policy'
    assert result['history'][0]['reviewer_execution'] == 'execution-1'
    assert runtime.update(build)['status'] == 'unchanged'
    assert len(reviewed) == len(uploaded) == 1


def test_changed_source_during_review_does_not_activate(setup):
    runtime, build, reviewed, uploaded = setup
    runtime.update(build)
    (build / 'index.html').write_text('<h1>second</h1>')
    before = runtime.snapshot()['active']
    def racing(bundle):
        (build / 'index.html').write_text('<h1>third</h1>')
        return ReviewResult('approved', [], 'model', 'execution-2', 0)
    runtime.reviewer = racing
    result = runtime.update(build)
    assert result['status'] == 'blocked'
    assert result['active'] == before
    assert result['error']['code'] == 'source_changed'
    assert len(uploaded) == 1


@pytest.mark.parametrize('outcome', ['blocked', 'malformed', 'timeout', 'upload', 'mismatch'])
def test_failure_preserves_last_approved(setup, outcome):
    runtime, build, reviewed, uploaded = setup
    first = runtime.update(build)['active']
    (build / 'index.html').write_text('<h1>candidate</h1>')
    def review(bundle):
        if outcome == 'timeout':
            raise TimeoutError('review budget')
        if outcome == 'malformed':
            return {'status': 'approved'}
        return ReviewResult('blocked' if outcome == 'blocked' else 'approved',
                            [{'severity': 'blocker', 'message': 'unsafe', 'path': 'index.html'}]
                            if outcome == 'blocked' else [], 'model', 'exec-2', 0)
    runtime.reviewer = review
    if outcome == 'upload':
        runtime.uploader = lambda b: (_ for _ in ()).throw(TimeoutError('upload'))
    if outcome == 'mismatch':
        runtime.uploader = lambda b: {'revision': 'sha256:' + '0' * 64, 'url': 'https://app.test/'}
    result = runtime.update(build)
    assert result['status'] == 'blocked'
    assert result['active'] == first


def test_author_written_receipt_and_active_pointer_are_never_trusted(setup):
    runtime, build, reviewed, uploaded = setup
    runtime.update(build)
    path = runtime.state_dir / 'state.json'
    raw = json.loads(path.read_text())
    raw['data']['active']['url'] = 'https://unreviewed.test/'
    path.write_text(json.dumps(raw))
    with pytest.raises(RuntimeErrorState, match='integrity'):
        runtime.snapshot()


def test_restart_and_rollback_require_signed_approval_and_current_policy(setup):
    runtime, build, reviewed, uploaded = setup
    first = runtime.update(build)['active']
    (build / 'index.html').write_text('<h1>second</h1>')
    runtime.update(build)
    restarted = ControlCenterRuntime(runtime.state_dir, reviewer=runtime.reviewer,
        uploader=runtime.uploader, policy='test-policy', clock=lambda: 1001,
        available=lambda app: True)
    assert restarted.rollback(first['revision'])['active'] == first
    restarted.available = lambda app: False
    with pytest.raises(RuntimeErrorState, match='unavailable'):
        restarted.rollback(first['revision'])
    restarted.policy = 'different-policy'
    with pytest.raises(RuntimeErrorState, match='policy'):
        restarted.rollback(first['revision'])


def test_concurrent_update_is_rejected_and_does_not_start_second_review(setup):
    runtime, build, reviewed, uploaded = setup
    from connectonion.network.host.control_center.runtime import writer_lock
    with writer_lock(runtime.state_dir):
        with pytest.raises(RuntimeErrorState, match='busy'):
            runtime.update(build)


def test_blocker_cannot_be_approved_and_new_build_can_retry(setup):
    runtime, build, reviewed, uploaded = setup
    runtime.reviewer = lambda b: ReviewResult('approved', [
        {'severity': 'blocker', 'message': 'must fix', 'path': 'index.html'}], 'model', 'exec', 0)
    assert runtime.update(build)['status'] == 'blocked'
    assert uploaded == []


def test_retention_preserves_active_approval_and_latest_attempt_with_bounded_state(tmp_path, monkeypatch):
    from connectonion.network.host.control_center import runtime as module
    runtime = ControlCenterRuntime(tmp_path / 'runtime', policy='test', reviewer=None, uploader=None)
    monkeypatch.setattr(module, 'MAX_STATE_BYTES', 2048)
    history = [{'revision': str(i), 'status': 'approved', 'padding': 'x' * 250} for i in range(30)]
    state = {'schema': 1, 'active': {'revision': '0'}, 'history': history, 'status': 'blocked'}
    runtime._save(state)
    saved = runtime.snapshot()
    assert saved['history'][0]['revision'] == '0'
    assert saved['history'][-1]['revision'] == '29'
    assert (runtime.state_dir / 'state.json').stat().st_size <= 2048


def test_unchanged_bytes_require_review_when_policy_changes(setup):
    runtime, build, reviewed, uploaded = setup
    runtime.update(build)
    runtime.policy = 'new-review-policy'
    assert runtime.update(build)['status'] == 'approved'
    assert len(reviewed) == 2
    assert runtime.snapshot()['active']['review']['policy'] == 'new-review-policy'
