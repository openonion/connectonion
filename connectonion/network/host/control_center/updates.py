"""Durable, coalesced triggers for the single Control Center review operation.

The Host's existing minute tick calls this object. Its independent queue lock
lets new events accumulate while the writer reviews a build. Only internal Host
events are accepted; arbitrary inbound mail/provider scheduling is not implied.
"""
import hashlib
import hmac
import json
import math
import os
import re
import time
import uuid
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from ..schedule import Entry, is_due, _last_occurrence
from .bundle import canonical
from .runtime import RuntimeErrorState, _read_private, atomic_private, writer_lock

EVENTS = {'agent.turn.completed', 'agent.skill.completed', 'control_center.source.changed'}
DEFAULT = {'enabled': False, 'every_seconds': None, 'at': None, 'tz': 'UTC',
           'events': [], 'debounce_seconds': 60, 'max_attempts_per_day': 24,
           'last_attempt': None, 'last_success': None, 'last_error': None,
           'last_status': 'never', 'last_revision': None, 'next_run': None,
           'seen': {}, 'pending': None, 'running': None, 'daily': {}}
SETTINGS = {'enabled', 'every_seconds', 'at', 'tz', 'events', 'debounce_seconds', 'max_attempts_per_day'}


class ControlCenterUpdates:
    def __init__(self, runtime, build_dir, *, generator, entry='index.html', capabilities=()):
        self.runtime, self.build_dir, self.generator = runtime, build_dir, generator
        self.entry, self.capabilities = entry, capabilities
        self.path = runtime.state_dir / 'updates.json'

    def _load(self):
        if not self.path.exists():
            return json.loads(json.dumps(DEFAULT))
        try:
            envelope = json.loads(_read_private(self.path, 256 * 1024))
            data = envelope['data']
            mac = hmac.new(self.runtime._key, canonical(data), hashlib.sha256).hexdigest()
            if not hmac.compare_digest(mac, envelope['mac']):
                raise ValueError('mac')
            return data
        except (ValueError, KeyError, TypeError) as exc:
            raise RuntimeErrorState('Update queue integrity verification failed') from exc

    def _save(self, state):
        data = canonical(state)
        if len(data) > 250 * 1024:
            raise RuntimeErrorState('Update queue exceeds limit')
        mac = hmac.new(self.runtime._key, data, hashlib.sha256).hexdigest()
        atomic_private(self.path, canonical({'data': state, 'mac': mac}))

    def snapshot(self):
        state = self._load()
        return {key: value for key, value in state.items() if key not in {'seen', 'daily'}}

    def configure(self, settings):
        if not isinstance(settings, dict) or set(settings) - SETTINGS:
            raise ValueError('Unsupported update setting')
        with writer_lock(self.runtime.state_dir, 'updates.lock'):
            state = {**self._load(), **settings}
            self._validate(state)
            state['next_run'] = self._next(state, state['last_attempt'] or time.time())
            self._save(state)
        return self.snapshot()

    def _validate(self, state):
        every, at = state['every_seconds'], state['at']
        if type(state['enabled']) is not bool:
            raise ValueError('enabled must be true or false')
        if every is not None and (type(every) is not int or not 60 <= every <= 604800):
            raise ValueError('every_seconds must be 60–604800')
        if at is not None and (not isinstance(at, str) or not re.fullmatch(r'(?:[01]\d|2[0-3]):[0-5]\d', at)):
            raise ValueError('at must be HH:MM')
        if every is not None and at is not None:
            raise ValueError('Choose every_seconds or at')
        try:
            ZoneInfo(state['tz'])
        except (ZoneInfoNotFoundError, TypeError, ValueError) as exc:
            raise ValueError('Unknown schedule timezone') from exc
        if (not isinstance(state['events'], list)
                or any(not isinstance(event, str) or event not in EVENTS for event in state['events'])):
            raise ValueError('Unsupported internal event')
        if type(state['debounce_seconds']) is not int or not 0 <= state['debounce_seconds'] <= 300:
            raise ValueError('debounce_seconds must be 0–300')
        if type(state['max_attempts_per_day']) is not int or not 1 <= state['max_attempts_per_day'] <= 96:
            raise ValueError('max_attempts_per_day must be 1–96')

    def enqueue(self, event, event_id, *, source='host', now=None):
        now = time.time() if now is None else now
        if source == 'control_center':
            return False
        if event not in EVENTS or not isinstance(event_id, str) or not 1 <= len(event_id) <= 128:
            raise ValueError('Invalid internal event')
        with writer_lock(self.runtime.state_dir, 'updates.lock'):
            state = self._load()
            state['seen'] = {key: at for key, at in state['seen'].items() if at > now - 7 * 86400}
            key = event + ':' + event_id
            if key in state['seen'] or not state['enabled'] or event not in state['events']:
                return False
            state['seen'][key] = now
            state['seen'] = dict(sorted(state['seen'].items(), key=lambda item: item[1])[-1024:])
            pending = state['pending'] or {'first_at': now, 'count': 0}
            pending.update(due_at=min(now + state['debounce_seconds'], pending['first_at'] + 300),
                           event=event, event_id=event_id, count=min(pending['count'] + 1, 1024))
            state['pending'] = pending
            self._save(state)
        return True

    def _entry(self, state):
        return Entry(name='control-center', run='update_control_center',
                     interval=timedelta(seconds=state['every_seconds']) if state['every_seconds'] else None,
                     at=state['at'], tz=state['tz'])

    def _next(self, state, now):
        if not state['enabled']:
            return None
        if state['every_seconds']:
            return now + state['every_seconds']
        if state['at']:
            instant = datetime.fromtimestamp(now, timezone.utc)
            candidates = [_last_occurrence(self._entry(state), instant + timedelta(days=n)) for n in (1, 2)]
            return min(moment.timestamp() for moment in candidates if moment and moment.timestamp() > now)
        return None

    def _due(self, state, now):
        if state['pending'] and state['pending']['due_at'] <= now:
            return 'event'
        if state['every_seconds'] or state['at']:
            last = datetime.fromtimestamp(state['last_attempt'], timezone.utc) if state['last_attempt'] is not None else None
            if is_due(self._entry(state), last, datetime.fromtimestamp(now, timezone.utc)):
                return 'schedule'
        return None

    def _claim(self, now, manual):
        with writer_lock(self.runtime.state_dir, 'updates.lock'):
            state = self._load()
            if state['running']:
                try:
                    os.kill(state['running']['pid'], 0)
                except PermissionError:
                    return None
                except ProcessLookupError:
                    state.update(running=None, last_status='interrupted',
                                 last_error='Previous process stopped during update; retry manually')
                    self._save(state)
                else:
                    return None
                if not manual:
                    return None
            if state['last_status'] == 'interrupted' and not manual:
                return None
            trigger = 'manual' if manual else (self._due(state, now) if state['enabled'] else None)
            if trigger is None:
                return None
            day = datetime.fromtimestamp(now, timezone.utc).date().isoformat()
            daily = state['daily'].get(day, {'attempts': 0, 'cost_usd': 0})
            if daily['attempts'] >= state['max_attempts_per_day'] or daily['cost_usd'] >= 2:
                state.update(last_status='budget_limited', last_error='Daily update budget reached')
                self._save(state)
                return None
            daily['attempts'] += 1
            state['daily'] = {day: daily}
            claim = {'id': str(uuid.uuid4()), 'pid': os.getpid(), 'started_at': now,
                     'trigger': trigger, 'event_id': (state['pending'] or {}).get('event_id')}
            state.update(running=claim, last_attempt=now, last_status='running', last_error=None,
                         pending=None, next_run=self._next(state, now))
            self._save(state)
            return claim

    def tick(self, *, now=None):
        return self._run(time.time() if now is None else now, manual=False)

    def manual(self, *, now=None):
        result = self._run(time.time() if now is None else now, manual=True)
        if result is None:
            raise RuntimeErrorState('Control Center update is busy or its daily budget is exhausted')
        return result

    def _run(self, now, manual):
        claim = self._claim(now, manual)
        if claim is None:
            return None
        return self.execute(claim)

    def execute(self, claim, *, generate=True):
        now = claim['started_at']
        cost, revision, error = 0, None, None
        try:
            # A fresh normal author turn edits the build; only the runtime below
            # can review/activate it. Its own completion events are excluded.
            generated = self.generator('Update the Control Center build for ' + claim['trigger'] +
                '. Follow CONTROL_CENTER.md. Make useful changes only; leave code unchanged if no update is needed.') if generate else None
            if isinstance(generated, dict):
                cost = float(generated.get('cost_usd', 0))
                if not math.isfinite(cost) or cost < 0:
                    cost = 0
                    raise RuntimeErrorState('Author usage could not be verified')
                if cost > 0.50:
                    raise RuntimeErrorState('Author cost limit exceeded; review was not started')
            result = self.runtime.update(self.build_dir, entry=self.entry, capabilities=self.capabilities,
                                         trigger=claim['trigger'], event_id=claim['event_id'])
            status = result['status']
            error = result.get('error')
            revision = (result.get('active') or {}).get('revision')
            if status != 'unchanged' and result.get('history'):
                cost += result['history'][-1].get('cost_usd', 0)
        except Exception as exc:
            status, error = 'failed', {'code': type(exc).__name__, 'message': 'Control Center update failed'}
        with writer_lock(self.runtime.state_dir, 'updates.lock'):
            state = self._load()
            if not state['running'] or state['running']['id'] != claim['id']:
                raise RuntimeErrorState('Update writer ownership changed')
            state.update(running=None, last_status=status, last_error=error, last_revision=revision)
            if status in {'approved', 'unchanged'}:
                state['last_success'] = now
            day = datetime.fromtimestamp(now, timezone.utc).date().isoformat()
            state['daily'][day]['cost_usd'] += max(0, cost)
            self._save(state)
        return self.snapshot()
