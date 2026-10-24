"""Direct co-ai subprocess attempts in existing run records, not provider calls.

The routine allowance is reserved before work; it is deliberately independent.
Custom callbacks and unobserved/legacy work cannot supply execution proof here.
"""
from contextlib import contextmanager
from contextvars import ContextVar

from .files import write_json

_ACTIVE = ContextVar('rem_execution_record', default=None)
COUNTERS = ('attempts', 'completed', 'failed', 'in_flight')
BOUNDARY = 'direct-co-ai-subprocess'
MAX_COUNT = 2**53 - 1


def begin(record, path):
    record.setdefault('execution', {'schema': 1, 'boundary': BOUNDARY,
                                    **dict.fromkeys(COUNTERS, 0), 'stage_attempts': {}})
    parent = _ACTIVE.get()
    if parent and parent[0]['id'] != record['id']:
        record['parent_run_id'] = parent[0]['id']
    return _ACTIVE.set((record, path))


def end(token):
    _ACTIVE.reset(token)


@contextmanager
def capture(record, path):
    token = begin(record, path)
    try:
        yield
    finally:
        end(token)


@contextmanager
def harness_attempt(stage):
    active = _ACTIVE.get()
    if active is None:
        yield
        return
    record, path = active
    evidence = record['execution']
    evidence['attempts'] += 1
    evidence['in_flight'] += 1
    stages = evidence['stage_attempts']
    stages[stage] = stages.get(stage, 0) + 1
    write_json(path, record)  # Persist before the subprocess can start or hang.
    outcome = 'failed'
    try:
        yield
        outcome = 'completed'
    finally:
        evidence['in_flight'] -= 1
        evidence[outcome] += 1
        write_json(path, record)


def _valid(evidence):
    return (isinstance(evidence, dict) and type(evidence.get('schema')) is int and evidence['schema'] == 1
            and evidence.get('boundary') == BOUNDARY
            and all(type(evidence.get(k)) is int and 0 <= evidence[k] <= MAX_COUNT for k in COUNTERS)
            and evidence['attempts'] == sum(evidence[k] for k in COUNTERS[1:]))


def summary(runs):
    """A lower bound over recorded direct attempts; never infer API calls/legacy zero."""
    totals = dict.fromkeys(COUNTERS, 0)
    known = unknown = 0
    for run in runs:
        evidence = run.get('execution')
        if not _valid(evidence) or any(totals[k] + evidence[k] > MAX_COUNT for k in COUNTERS):
            unknown += 1
            continue
        known += 1
        for key in COUNTERS:
            totals[key] += evidence[key]
    return {**totals, 'records_with_evidence': known, 'records_without_evidence': unknown,
            'provider_model_calls': None, 'scope': BOUNDARY}
