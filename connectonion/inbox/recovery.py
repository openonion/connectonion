"""Reconcile known conversations after a listener restart or connection gap.

History is a second delivery path, not a replacement for the WebSocket. Every
record goes through the same durable inbox deduplication. The checkpoint only
advances after a run finishes. No chat discovery or old-history import occurs.

A run happens at start and after a reconnect, never on a timer: every history
page is an API call against the tenant's quota, and the listener is push-driven.
One run makes at most CALL_BUDGET calls, newest conversations first, at most
PAGES_PER_CONTAINER per conversation. A run that fails is not retried until the
next reconnect or restart, so a permanent error is one log line, not 23k (#2690).
"""
import json
import os
import threading
import time
from types import SimpleNamespace as NS
from urllib.parse import urlencode

from .store import _sync_directory


class MissingScope(RuntimeError):
    """The app lacks a permission only an admin can grant; retrying cannot fix it."""


class LarkError(RuntimeError):
    """Feishu or Lark answered with a non-zero code. `code` is theirs."""

    def __init__(self, message, code=None):
        super().__init__(message)
        self.code = code


# Lark refusing one container rather than the whole call: 230001 is an invalid
# container_id, 230002 a chat the bot is no longer in. Skip that one, keep going.
CONTAINER_REJECTED = {230001, 230002}
CALL_BUDGET = 40
PAGES_PER_CONTAINER = 2
# A message this close to a connect or disconnect may have raced it.
SLACK_SECONDS = 5
MISSED_LIVE = ('message {id} reached the bot but not this listener — another client may be '
               'connected with this app_id (Lark sends each event to only one client)')


class HistoryRecovery:
    """One worker owned by the single listener for this inbox directory."""

    def __init__(self, provider, inbox, *, started_at=None, raw=False):
        self.provider, self.inbox, self.raw = provider, inbox, raw
        self.state = inbox.root / 'recovery.json'
        self.guard = threading.RLock()
        self.chat_types = {}
        if self.state.exists():
            saved = json.loads(self.state.read_text())
            self.since = saved['since']
            self.through = saved['through']
            self.chat_types = saved.get('chat_types', {})
            if not isinstance(self.since, int) or not isinstance(self.through, int):
                raise ValueError('Invalid recovery checkpoint; preserve it and repair before restarting')
        else:
            self.since = self.through = int(time.time() if started_at is None else started_at)
            self._save(self.through)
        self.pending, self.stopped = threading.Event(), threading.Event()
        self.worker = None
        self.calls = 0
        # When this listener's socket was up: from live_from, minus the gaps.
        # A recovered message from inside that span reached someone else.
        self.live_from = None
        self.gaps = []

    def _save(self, through):
        with self.guard:
            self._write_state(through)

    def note_chat(self, chat, chat_type):
        if chat_type not in ('group', 'p2p'):
            return
        with self.guard:
            if self.chat_types.get(chat) != chat_type:
                self.chat_types[chat] = chat_type
                self._write_state(self.through)

    def _write_state(self, through):
        temp = self.inbox.tmp / 'recovery.json'
        with temp.open('w') as handle:
            json.dump({'since': self.since, 'through': through, 'chat_types': self.chat_types}, handle)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, self.state)
        _sync_directory(self.inbox.root)
        self.through = through

    def _containers(self):
        """Known conversations, most recently active first. Only a real thread
        id (omt_) is a thread container; a reply's root_id is a message id, and
        Lark rejects it as one (#2690)."""
        found = {}
        if self.inbox.received.exists():
            for line in reversed(self.inbox.received.read_text().splitlines()):
                try:
                    row = json.loads(line)
                except ValueError:
                    continue  # A torn journal tail is handled by inbox recovery.
                if row.get('chat'):
                    if _is_thread(row.get('thread')):
                        found.setdefault(('thread', row['thread']), row['chat'])
                    found.setdefault(('chat', row['chat']), row['chat'])
        with self.guard:
            for chat, kind in self.chat_types.items():
                if kind in ('p2p', 'group'):
                    found.setdefault(('chat', chat), chat)
        return found

    def _pages(self, kind, identifier, until):
        """Newest first, stopping at the checkpoint, the page cap or the budget."""
        query = {'container_id_type': kind, 'container_id': identifier,
                 'page_size': 50, 'sort_type': 'ByCreateTimeDesc'}
        if kind == 'chat':
            query.update(start_time=max(0, self.through - 2), end_time=until + 1)
        floor = max(self.since, self.through - 2)
        tokens = set()
        for _ in range(PAGES_PER_CONTAINER):
            if self.stopped.is_set():
                raise RuntimeError('History recovery stopped before completion')
            if self.calls >= CALL_BUDGET:
                return
            self.calls += 1
            body = self.provider._get('/open-apis/im/v1/messages?' + urlencode(query))
            if not isinstance(body.get('items'), list):
                raise ValueError('History response has no message list')
            yield from body['items']
            if not body.get('has_more') or any(
                    int(row.get('create_time') or 0) / 1000 < floor for row in body['items']):
                return
            token = body.get('page_token')
            if not token or token in tokens:
                raise ValueError('History pagination did not advance')
            tokens.add(token)
            query['page_token'] = token
        self.inbox.log(f'history recovery read {PAGES_PER_CONTAINER} pages of {kind} {identifier}; '
                       'older messages in it are not checked this run')

    def _message(self, row, chat):
        if row.get('deleted') or row.get('sender', {}).get('sender_type') != 'user':
            return None
        if not row.get('message_id') or not row.get('create_time'):
            raise ValueError('History message is missing identity or timestamp')
        timestamp = int(row['create_time']) / 1000
        if timestamp < max(self.since, self.through - 2):
            return None
        sender = row['sender']
        mentions = [NS(key=m.get('key'), name=m.get('name'), id=NS(open_id=m.get('id')))
                    for m in row.get('mentions', [])]
        message = NS(message_id=row['message_id'], chat_id=chat,
                     chat_type=self.chat_types.get(chat, row.get('chat_type', 'group')),
                     message_type=row.get('msg_type'), content=row.get('body', {}).get('content'),
                     create_time=row['create_time'], thread_id=row.get('thread_id'),
                     root_id=row.get('root_id'), mentions=mentions)
        sender_id = NS(**{sender.get('id_type', 'open_id'): sender.get('id')})
        result = self.provider.to_message(NS(event=NS(message=message,
                    sender=NS(sender_type='user', sender_id=sender_id))))
        # History may expose more group traffic than group_at_msg events.
        # Never turn unrelated conversation history into new agent work.
        if result is not None and not result.mentioned:
            return None
        if self.raw and result is not None:
            result.raw = row
        return result

    def reconcile(self, *, until=None):
        until = int(time.time() if until is None else until)
        containers = self._containers()
        if containers and not self.provider._bot_open_id:
            self.provider.bot_info()
            if not self.provider._bot_open_id:
                raise ValueError('Cannot verify bot identity for history mention filtering')
        queue = list(containers.items())
        visited = set()
        count = 0
        self.calls = 0
        while queue:
            if self.calls >= CALL_BUDGET:
                self.inbox.log(f'history recovery used its budget of {CALL_BUDGET} calls; '
                               f'{len(queue)} older conversation(s) not checked this run')
                break
            (kind, identifier), chat = queue.pop(0)
            if (kind, identifier) in visited:
                continue
            visited.add((kind, identifier))
            try:
                for row in self._pages(kind, identifier, until):
                    if _is_thread(row.get('thread_id')) and ('thread', row['thread_id']) not in visited:
                        queue.insert(0, (('thread', row['thread_id']), chat))
                    count += self._recover(row, chat, until)
            except LarkError as exc:
                if exc.code not in CONTAINER_REJECTED:
                    raise
                self.inbox.log(f'history recovery skipped {kind} {identifier}: {exc}')
        self._save(until)
        (self.inbox.root / 'recovery-error.txt').unlink(missing_ok=True)
        self.inbox.log(f'history recovery complete: {count} new message(s), {self.calls} API call(s)')
        return count

    def _recover(self, row, chat, until):
        message = self._message(row, chat)
        if not message or int(row['create_time']) / 1000 > until:
            return 0
        if not self.inbox.deliver(message, raw=self.raw):
            return 0
        if self._missed_live(int(row['create_time']) / 1000):
            warning = MISSED_LIVE.format(id=message.id)
            self.inbox.log(f'WARNING {warning}')
            (self.inbox.root / 'missed-live.txt').write_text(f'{message.at} {warning}\n')
        return 1

    def _missed_live(self, at):
        """Sent while this listener's socket was up, yet only history has it."""
        if self.live_from is None or at < self.live_from + SLACK_SECONDS:
            return False
        return not any(start - SLACK_SECONDS <= at <= (end or float('inf')) + SLACK_SECONDS
                       for start, end in self.gaps)

    def disconnected(self, at=None):
        self.gaps.append([time.time() if at is None else at, None])

    def connected(self, at=None):
        at = time.time() if at is None else at
        if self.live_from is None:
            self.live_from = at
        elif self.gaps and self.gaps[-1][1] is None:
            self.gaps[-1][1] = at

    def start(self):
        self.pending.set()
        self.worker = threading.Thread(target=self._work, daemon=True)
        self.worker.start()

    def request(self):
        self.pending.set()

    def _work(self):
        while not self.stopped.is_set():
            if not self.pending.wait(1):
                continue
            if self.stopped.is_set():
                return
            self.pending.clear()
            try:
                self.reconcile()
            except MissingScope as exc:
                (self.inbox.root / 'recovery-error.txt').write_text(str(exc))
                self.inbox.log(f'history recovery stopped: {exc}. Grant that scope to the app in the '
                               'developer console (a tenant admin may need to approve it), then restart '
                               'the listener. Live messages still arrive.')
                return
            except Exception as exc:
                # No timer: a retry every minute was 23k identical lines and
                # 23k quota calls for an error that never changed (#2690).
                (self.inbox.root / 'recovery-error.txt').write_text(str(exc))
                self.inbox.log(f'history recovery incomplete; checkpoint retained: {exc}. '
                               'It runs again at the next reconnect or restart. Live messages still arrive.')

    def stop(self):
        self.stopped.set()
        self.pending.set()
        if self.worker is not None:
            # Do not release the listener lock while a history writer is alive.
            self.worker.join()


def _is_thread(identifier):
    return isinstance(identifier, str) and identifier.startswith('omt_')
