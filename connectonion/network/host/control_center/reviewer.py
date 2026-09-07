"""Run the designated review skill in a fresh, time-bounded Agent process.

No author session, tools, callbacks, or history enter that process. The model
returns findings; the parent runtime supplies provenance and performs activation.
"""
import base64
import contextlib
import hashlib
import io
import json
import math
import os
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path

from ....core.usage import DEFAULT_MODEL

from .bundle import Bundle, canonical, media_type
from .runtime import ReviewResult, RuntimeErrorState

MAX_REVIEW_BYTES = 512 * 1024
MAX_REPLY_BYTES = 128 * 1024
POLICY_PATH = Path(__file__).parents[3] / 'useful_skills/control-center-review/SKILL.md'
EXECUTABLE_TYPES = {'text/html', 'text/javascript', 'text/css', 'image/svg+xml',
                    'application/json', 'text/plain', 'application/wasm'}


def review_payload(bundle: Bundle, *, max_bytes=MAX_REVIEW_BYTES) -> dict:
    files, size = {}, 0
    for path, data in bundle.files.items():
        kind = media_type(path)
        if kind not in EXECUTABLE_TYPES:
            continue  # Non-executable binary assets remain identified in the manifest.
        size += len(data)
        if size > max_bytes:
            raise RuntimeErrorState('Executable source exceeds review byte budget')
        if kind == 'application/wasm':
            files[path] = {'base64': base64.b64encode(data).decode('ascii')}
        else:
            try:
                files[path] = {'text': data.decode('utf-8')}
            except UnicodeDecodeError as exc:
                raise RuntimeErrorState('Executable source must be UTF-8') from exc
    return {'revision': bundle.revision, 'manifest': bundle.manifest, 'files': files}


class SkillReviewer:
    """One fresh Agent, one model call, no automatic review retries."""

    def __init__(self, *, model=DEFAULT_MODEL, timeout=90, max_cost_usd=0.25):
        self.model, self.timeout, self.max_cost_usd = model, timeout, max_cost_usd
        self.policy = POLICY_PATH.read_text()
        self.policy_id = 'control-center-review/1:' + hashlib.sha256(canonical({
            'skill': self.policy, 'model': model, 'max_source_bytes': MAX_REVIEW_BYTES,
            'max_output_tokens': 4096, 'timeout': timeout,
            'activation_cost_limit': max_cost_usd})).hexdigest()

    def __call__(self, bundle: Bundle) -> ReviewResult:
        payload = {'bundle': review_payload(bundle), 'policy': self.policy, 'model': self.model}
        execution = str(uuid.uuid4())
        # An absolute package root works for both an installed wheel and a checkout.
        # It is set by the runtime, never supplied by the authored app.
        package_root = str(Path(__file__).parents[4])
        environment = dict(os.environ, PYTHONPATH=package_root)
        with tempfile.TemporaryDirectory(prefix='co-control-review-') as directory:
            try:
                completed = subprocess.run(
                    [sys.executable, '-m', __name__, '--worker'],
                    input=json.dumps(payload), text=True, capture_output=True,
                    cwd=directory, env=environment, timeout=self.timeout, check=False)
            except subprocess.TimeoutExpired as exc:
                raise TimeoutError('Control Center review time budget exceeded') from exc
        if completed.returncode or len(completed.stdout.encode()) > MAX_REPLY_BYTES:
            raise RuntimeErrorState('Reviewer worker did not return a bounded result')
        try:
            envelope = json.loads(completed.stdout)
            result, cost = envelope['result'], envelope['cost_usd']
            if (not isinstance(result, dict) or set(result) != {'schema', 'revision', 'status', 'findings'}
                    or type(result['schema']) is not int or result['schema'] != 1
                    or result['revision'] != bundle.revision or type(cost) not in (int, float)
                    or not math.isfinite(cost) or not 0 <= cost <= self.max_cost_usd):
                raise ValueError('result does not meet review contract')
            review = ReviewResult(result['status'], result['findings'], self.model, execution, cost)
            approved = review.validate()
            if result['status'] == 'approved' and not approved:
                raise ValueError('approval contains blocker')
            if any(item['path'] and item['path'] not in bundle.files for item in review.findings):
                raise ValueError('finding names absent file')
            return review
        except (ValueError, KeyError, TypeError) as exc:
            raise RuntimeErrorState('Malformed or over-budget reviewer result') from exc


def _worker():
    # Core's normal Agent/LLM runtime invokes the skill; this is not a review service.
    raw = sys.stdin.buffer.read(4 * MAX_REVIEW_BYTES + 1)
    if len(raw) > 4 * MAX_REVIEW_BYTES:
        raise RuntimeErrorState('Review request exceeds limit')
    request = json.loads(raw)
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        from connectonion import Agent
        from connectonion.core.llm import create_llm
        llm = create_llm(request['model'])
        if getattr(llm, 'client', None) is not None:
            llm.client = llm.client.with_options(max_retries=0, timeout=80)
        complete = llm.complete
        llm.complete = lambda messages, tools=None, **kw: complete(
            messages, tools=tools, max_tokens=4096, **kw)
        agent = Agent('control-center-review', llm=llm, tools=[],
                      system_prompt=request['policy'], max_iterations=1,
                      quiet=True, log=False, state_dir=Path.cwd() / 'state')
        answer = agent.input(json.dumps(request['bundle']))
    result = json.loads(answer)
    sys.stdout.write(json.dumps({'result': result, 'cost_usd': agent.total_cost}))


if __name__ == '__main__':
    try:
        if sys.argv[1:] != ['--worker']:
            raise RuntimeErrorState('Use the Control Center runtime to invoke review')
        _worker()
    except Exception:
        # Parent records a failed review, without leaking provider responses.
        sys.exit(1)
