"""Private, profile-bound paging snapshots and restartable operation receipts."""

import hashlib
import json
from pathlib import Path
import re
import time
from uuid import uuid4

from ..environment import global_config_dir
from .synology_profiles import private_json, read_private_json, ProfileError
from .synology_transport import SynologyError

TTL = 15 * 60
MAX_RECORD_BYTES = 4 * 1024 * 1024


class SynologyState:
    def __init__(self, identity: str, directory: Path | None = None):
        self.identity = hashlib.sha256(identity.encode()).hexdigest()
        self.directory = directory or global_config_dir() / 'synology' / 'state'

    def path(self, token: str, kind: str) -> Path:
        if not re.fullmatch('[a-f0-9]{32}', token or '') or kind not in {'cursor','listing','operation'}:
            raise SynologyError('Invalid saved NAS reference; run the listing again.', 'stale_cursor')
        return self.directory / kind / f'{token}.json'

    def save(self, kind: str, value: dict, token: str | None = None) -> str:
        token = token or uuid4().hex
        data = {'schema_version':1, 'identity':self.identity, 'created_at':time.time(), **value}
        if len(json.dumps(data).encode()) > MAX_RECORD_BYTES:
            raise SynologyError('NAS result exceeds the local snapshot limit; narrow the search scope.', 'response_too_large')
        path = self.path(token, kind)
        private_json(path, data)
        # Completed/unknown operations are never forgotten automatically: an
        # expired receipt must not cause an ambiguous write to be resubmitted.
        if kind != 'operation':
            records = sorted(path.parent.glob('*.json'), key=lambda p: p.lstat().st_mtime, reverse=True)
            for old in records[128:]:
                old.unlink(missing_ok=True)
        return token

    def read(self, kind: str, token: str, params: dict | None = None) -> dict:
        try:
            data = read_private_json(self.path(token, kind), limit=MAX_RECORD_BYTES)
        except ProfileError:
            raise SynologyError('Saved NAS reference is missing, corrupt or not private; repeat the listing.', 'stale_cursor') from None
        age = time.time() - data.get('created_at', 0) if isinstance(data.get('created_at'), (int,float)) else TTL+1
        if (data.get('schema_version') != 1 or data.get('identity') != self.identity
                or (kind != 'operation' and not 0 <= age <= TTL)
                or (params is not None and params != data.get('params'))):
            raise SynologyError('Saved reference expired or belongs to another profile or query; repeat the original listing.', 'stale_cursor')
        return data

    def listing(self, items: list) -> str:
        return self.save('listing', {'paths':[item['path'] for item in items]})

    def resolve(self, reference: str, listing: str | None = None) -> str:
        if reference.startswith('/'):
            return reference
        if not reference.isascii() or not reference.isdigit() or not listing:
            raise SynologyError('Use a complete NAS path, or a numeric row with its explicit --listing ID.', 'listing_required')
        paths = self.read('listing', listing).get('paths')
        index = int(reference)-1
        if not isinstance(paths, list) or not 0 <= index < len(paths) or not isinstance(paths[index], str):
            raise SynologyError('That row is absent from the selected listing.', 'invalid_reference')
        return paths[index]
