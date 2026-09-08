"""Reconcile known conversations after a listener restart or connection gap.

History is a second delivery path, not a replacement for the WebSocket. Every
record goes through the same durable mailbox deduplication. The checkpoint only
advances after all pages succeed. No chat discovery or old-history import occurs.
"""
import json
import os
import threading
import time
from types import SimpleNamespace as NS
from urllib.parse import urlencode

from .mailbox import _sync_directory


class HistoryRecovery:
    """One worker owned by the single listener for this mailbox directory."""

    def __init__(self, provider, mailbox, *, started_at=None, raw=False):
        self.provider, self.mailbox, self.raw = provider, mailbox, raw
        self.state = mailbox.root / 'recovery.json'
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
        temp = self.mailbox.tmp / 'recovery.json'
        with temp.open('w') as handle:
            json.dump({'since': self.since, 'through': through, 'chat_types': self.chat_types}, handle)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, self.state)
        _sync_directory(self.mailbox.root)
        self.through = through

    def _containers(self):
        containers = {}
        if self.mailbox.inbox.exists():
            for line in self.mailbox.inbox.read_text().splitlines():
                try:
                    row = json.loads(line)
                except ValueError:
                    continue  # A torn journal tail is handled by mailbox recovery.
                if row.get('chat'):
                    containers[('chat', row['chat'])] = row['chat']
                    if row.get('thread'):
                        containers[('thread', row['thread'])] = row['chat']
        return containers

    def _pages(self, kind, identifier, until):
        query = {'container_id_type': kind, 'container_id': identifier,
                 'page_size': 50, 'sort_type': 'ByCreateTimeAsc'}
        if kind == 'chat':
            query.update(start_time=max(0, self.through - 2), end_time=until + 1)
        tokens = set()
        while not self.stopped.is_set():
            body = self.provider._get('/open-apis/im/v1/messages?' + urlencode(query))
            if not isinstance(body.get('items'), list):
                raise ValueError('History response has no message list')
            yield from body['items']
            if not body.get('has_more'):
                return
            token = body.get('page_token')
            if not token or token in tokens:
                raise ValueError('History pagination did not advance')
            tokens.add(token)
            query['page_token'] = token
        raise RuntimeError('History recovery stopped before completion')

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
        visited = set()
        count = 0
        while containers:
            (kind, identifier), chat = containers.popitem()
            if (kind, identifier) in visited:
                continue
            visited.add((kind, identifier))
            for row in self._pages(kind, identifier, until):
                if row.get('thread_id'):
                    containers[('thread', row['thread_id'])] = chat
                message = self._message(row, chat)
                if message and int(row['create_time']) / 1000 <= until:
                    count += self.mailbox.deliver(message, raw=self.raw)
        self._save(until)
        (self.mailbox.root / 'recovery-error.txt').unlink(missing_ok=True)
        self.mailbox.log(f'history recovery complete: {count} new message(s)')
        return count

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
            except Exception as exc:
                (self.mailbox.root / 'recovery-error.txt').write_text(str(exc))
                self.mailbox.log(f'history recovery incomplete; checkpoint retained: {exc}. '
                                 'Check bot history permissions and network; retrying in 60 seconds')
                if not self.stopped.wait(60):
                    self.pending.set()

    def stop(self):
        self.stopped.set()
        self.pending.set()
        if self.worker is not None:
            # Do not release the listener lock while a history writer is alive.
            self.worker.join()
